from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import desc
from routes import admin_required

from app import db
from models import Client, Invoice, Payment, SystemLog
from forms.clients import ClientForm, DeleteClientForm
from forms.operations import DeletePaymentForm, PaymentForm

clients_bp = Blueprint('clients', __name__, url_prefix='/clients')


@clients_bp.route('/')
@login_required
def index():
    # Get all clients with pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Filter parameters
    name_filter = request.args.get('name', '')
    
    # Base query
    query = Client.query
    
    # Apply filters if provided
    if name_filter:
        query = query.filter(Client.name.ilike(f'%{name_filter}%'))
    
    # Execute query with pagination
    clients = query.order_by(Client.name).paginate(page=page, per_page=per_page)
    
    return render_template('clients/index.html', clients=clients)


@clients_bp.route('/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add():
    form = ClientForm()
    
    if form.validate_on_submit():
        client = Client(
            name=form.name.data,
            phone=form.phone.data,
            email=form.email.data,
            address=form.address.data
        )
        
        # Log the creation
        log = SystemLog(
            action='client_create',
            details=f'إضافة عميل جديد: {client.name}',
            user_id=current_user.id
        )
        
        db.session.add(client)
        db.session.add(log)
        db.session.commit()
        
        flash(f'تم إضافة العميل {client.name} بنجاح', 'success')
        return redirect(url_for('clients.index'))
    
    return render_template('clients/add.html', form=form)


@clients_bp.route('/<int:client_id>')
@login_required
def view(client_id):
    client = Client.query.get_or_404(client_id)
    
    # Get all invoices for this client
    invoices = Invoice.query.filter_by(client_id=client_id).order_by(desc(Invoice.date)).all()
    
    # Get all payments for this client
    payments = Payment.query.filter_by(client_id=client_id).order_by(desc(Payment.payment_date)).all()
    
    # Calculate total purchased, total paid, and balance
    total_purchased = sum(invoice.total_amount for invoice in invoices if invoice.type == 'sale')
    total_returns = sum(invoice.total_amount for invoice in invoices if invoice.type == 'return')
    total_paid = sum(payment.amount for payment in payments)
    balance = total_purchased - total_returns - total_paid
    
    delete_client_form = DeleteClientForm()
    delete_payment_forms = {payment.id: DeletePaymentForm() for payment in payments}
    
    return render_template(
        'clients/view.html',
        client=client,
        invoices=invoices,
        payments=payments,
        total_purchased=total_purchased,
        total_returns=total_returns,
        total_paid=total_paid,
        balance=balance,
        delete_client_form=delete_client_form,
        delete_payment_forms=delete_payment_forms
    )


@clients_bp.route('/edit/<int:client_id>', methods=['GET', 'POST'])
@login_required
def edit(client_id):
    client = Client.query.get_or_404(client_id)
    form = ClientForm(obj=client)
    
    if form.validate_on_submit():
        # Update client details
        client.name = form.name.data
        client.phone = form.phone.data
        client.email = form.email.data
        client.address = form.address.data
        
        # Log the update
        log = SystemLog(
            action='client_edit',
            details=f'تعديل العميل: {client.name}',
            user_id=current_user.id
        )
        
        db.session.add(log)
        db.session.commit()
        
        flash(f'تم تحديث بيانات العميل {client.name} بنجاح', 'success')
        return redirect(url_for('clients.view', client_id=client.id))
    
    return render_template('clients/edit.html', form=form, client=client)


@clients_bp.route('/delete/<int:client_id>', methods=['POST'])
@login_required
@admin_required
def delete(client_id):
    form = DeleteClientForm()
    if not form.validate_on_submit():
        flash('خطأ في التحقق من صحة النموذج', 'danger')
        return redirect(url_for('clients.view', client_id=client_id))

    client = Client.query.get_or_404(client_id)
    
    # Get related data for logging
    invoice_count = len(client.invoices)
    payment_count = len(client.payments)
    
    # Log the deletion with details
    log = SystemLog(
        action='client_delete',
        details=f'حذف العميل: {client.name} مع {invoice_count} فاتورة و {payment_count} دفعة',
        user_id=current_user.id
    )
    
    db.session.add(log)
    db.session.delete(client)  # This will cascade delete all related records
    db.session.commit()
    
    flash(f'تم حذف العميل {client.name} وجميع السجلات المرتبطة به بنجاح', 'success')
    return redirect(url_for('clients.index'))

@clients_bp.route('/add_payment/<int:client_id>', methods=['GET', 'POST'])
@login_required
def add_payment(client_id):
    from forms.operations import PaymentForm
    
    client = Client.query.get_or_404(client_id)
    form = PaymentForm()
    
    # Populate invoice dropdown with this client’s invoices
    invoices = Invoice.query.filter_by(client_id=client_id).order_by(desc(Invoice.date)).all()
    form.invoice_id.choices = [(0, 'دفعة عامة (غير مرتبطة بفاتورة)')] + [(inv.id, inv.invoice_number) for inv in invoices]
    
    # For client payments, we can safely skip checking for invoice selection
    # and use the default choices that are already set in the form definition
    
    if form.validate_on_submit():
        if form.invoice_id.data == 0:
            # General payment: allocate to oldest unpaid invoices first
            payment_amount = round(float(form.amount.data), 2)
            remaining = payment_amount
            allocations = []
            invoices = Invoice.query.filter(
                Invoice.client_id == client_id,
                Invoice.type == 'sale',
                Invoice.status != 'paid'
            ).all()
            # Sort invoices by lowest remaining amount (not by date)
            invoices.sort(key=lambda inv: inv.calculate_remaining_amount())
            for inv in invoices:
                rem_amt = inv.calculate_remaining_amount()
                if rem_amt <= 0:
                    continue
                alloc = min(remaining, rem_amt)
                allocations.append((inv, alloc))
                remaining -= alloc
                if remaining <= 0:
                    break
            # If there is still remaining amount after all invoices are paid, add as unlinked
            if remaining > 0:
                allocations.append((None, remaining))
            # If there were no unpaid invoices at all, allocate the whole payment as unlinked
            if not allocations:
                allocations.append((None, payment_amount))
            # Create payments
            for inv2, amt in allocations:
                pay = Payment(
                    client_id=client_id,
                    amount=amt,
                    payment_date=form.payment_date.data,
                    payment_method=form.payment_method.data,
                    reference_number=form.reference_number.data,
                    notes=form.notes.data,
                    created_by=current_user.id
                )
                if inv2:
                    pay.invoice_id = inv2.id
                    db.session.add(pay)
                    inv2.update_status()
                else:
                    db.session.add(pay)
            # Log the payment
            log = SystemLog(
                action='payment_add',
                details=f'إضافة دفعة عامة من العميل {client.name}: {payment_amount} ج.م',
                user_id=current_user.id
            )
            db.session.add(log)
            db.session.commit()
            # Ensure all invoice statuses are up to date after all allocations
            for inv2, _ in allocations:
                if inv2:
                    inv2.update_status()
            db.session.commit()
            # Send Telegram notification
            from notifications import send_message
            msg = f'تم تسجيل دفعة عامة للعميل {client.name}: {payment_amount} ج.م'
            send_message(msg)
            flash(f'تم إضافة الدفعة العامة بمبلغ {payment_amount} ج.م بنجاح وربطها بأقل الفواتير المتبقية', 'success')
            return redirect(url_for('clients.view', client_id=client_id))
        else:
            # If payment is for a specific invoice
            payment = Payment(
                client_id=client_id,
                amount=form.amount.data,
                payment_date=form.payment_date.data,
                payment_method=form.payment_method.data,
                reference_number=form.reference_number.data,
                notes=form.notes.data,
                created_by=current_user.id,
                invoice_id=form.invoice_id.data
            )
            invoice = Invoice.query.get(form.invoice_id.data)
            invoice.update_status()
            # Log the payment
            log = SystemLog(
                action='payment_add',
                details=f'إضافة دفعة من العميل {client.name}: {payment.amount} ج.م',
                user_id=current_user.id
            )
            db.session.add(payment)
            db.session.add(log)
            db.session.commit()
            flash(f'تم إضافة الدفعة بمبلغ {payment.amount} ج.م بنجاح', 'success')
            return redirect(url_for('clients.view', client_id=client_id))
    
    return render_template('clients/add_payment.html', form=form, client=client)
