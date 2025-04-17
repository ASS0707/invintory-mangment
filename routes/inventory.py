from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import desc
from routes import admin_required

from app import db, app
from models import Product, SystemLog
from forms.inventory import ProductForm, DeleteProductForm, MergeProductsForm

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')


@inventory_bp.route('/')
@login_required
def index():
    # Get all products with pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Filter parameters
    name_filter = request.args.get('name', '')
    color_filter = request.args.get('color', '')
    material_filter = request.args.get('material', '')
    type_filter = request.args.get('type', '')
    
    # Base query: only products with stock > 0
    query = Product.query.filter(Product.quantity > 0)
    
    # Apply filters if provided
    if name_filter:
        query = query.filter(Product.name.ilike(f'%{name_filter}%'))
    if color_filter:
        query = query.filter(Product.color.ilike(f'%{color_filter}%'))
    if material_filter:
        query = query.filter(Product.material.ilike(f'%{material_filter}%'))
    if type_filter:
        query = query.filter(Product.type == type_filter)
    
    # Execute query with pagination
    products = query.order_by(desc(Product.updated_at)).paginate(page=page, per_page=per_page)
    
    # Fetch zero-stock products (same filters)
    zero_query = Product.query.filter(Product.quantity == 0)
    if name_filter:
        zero_query = zero_query.filter(Product.name.ilike(f'%{name_filter}%'))
    if color_filter:
        zero_query = zero_query.filter(Product.color.ilike(f'%{color_filter}%'))
    if material_filter:
        zero_query = zero_query.filter(Product.material.ilike(f'%{material_filter}%'))
    if type_filter:
        zero_query = zero_query.filter(Product.type == type_filter)
    zero_products = zero_query.order_by(desc(Product.updated_at)).all()
    
    merge_form = MergeProductsForm()
    return render_template('inventory/index_new.html', products=products, merge_form=merge_form, zero_products=zero_products)

@inventory_bp.route('/add-new-product', methods=['GET', 'POST'])
@login_required
@admin_required
def add_new_product():
    app.logger.debug(f"Method: {request.method}")
    
    if request.method == 'POST':
        try:
            app.logger.debug(f"Form data: {request.form}")
            
            # Get form data
            name = request.form.get('name')
            if not name:
                flash('اسم المنتج مطلوب', 'danger')
                return render_template('inventory/add_new.html')
                
            color = request.form.get('color')
            if not color:
                flash('لون المنتج مطلوب', 'danger')
                return render_template('inventory/add_new.html')
                
            material = request.form.get('material')
            if not material:
                flash('مادة المنتج مطلوبة', 'danger')
                return render_template('inventory/add_new.html')
            
            # Convert values with error handling
            try:
                quantity = int(request.form.get('quantity', 0))
            except ValueError:
                flash('الكمية يجب أن تكون رقم صحيح', 'danger')
                return render_template('inventory/add_new.html')
                
            product_type = request.form.get('type')
            if not product_type:
                flash('نوع المنتج مطلوب', 'danger')
                return render_template('inventory/add_new.html')
                
            try:
                finishing_cost = float(request.form.get('finishing_cost', 0))
            except ValueError:
                flash('تكلفة التشطيب يجب أن تكون رقم', 'danger')
                return render_template('inventory/add_new.html')
            
            printing_cost = 0
            if product_type == 'Printed':
                try:
                    printing_cost = float(request.form.get('printing_cost', 0))
                except ValueError:
                    flash('تكلفة الطباعة يجب أن تكون رقم', 'danger')
                    return render_template('inventory/add_new.html')
            
            app.logger.debug(f"Parsed data: {name}, {color}, {material}, {quantity}, {product_type}, {finishing_cost}, {printing_cost}")
            
            # Check if product with same name, color, and material exists
            existing_product = Product.query.filter(
                Product.name.ilike(name.strip()),
                Product.color.ilike(color.strip()),
                Product.material.ilike(material.strip()),
                Product.type == product_type
            ).first()
            
            if existing_product:
                # Update existing product
                existing_product.quantity += quantity
                # Update other properties if they've changed
                existing_product.finishing_cost = finishing_cost
                if product_type == 'Printed':
                    existing_product.printing_cost = printing_cost
                
                # Log the update
                log = SystemLog(
                    action='product_update',
                    details=f'تحديث كمية المنتج: {existing_product.name} ({existing_product.color}), الكمية المضافة: {quantity}',
                    user_id=current_user.id
                )
                db.session.add(log)
                db.session.commit()
                
                flash(f'تم تحديث كمية المنتج {existing_product.name} بنجاح', 'success')
                app.logger.debug(f"Updated product {existing_product.name}")
                return redirect(url_for('inventory.index'))
            else:
                # Create new product
                product = Product(
                    name=name.strip(),
                    color=color.strip(),
                    material=material.strip(),
                    quantity=quantity,
                    type=product_type,
                    finishing_cost=finishing_cost,
                    printing_cost=printing_cost
                )
                
                # Log the creation
                log = SystemLog(
                    action='product_create',
                    details=f'إنشاء منتج جديد: {product.name} ({product.color})',
                    user_id=current_user.id
                )
                
                db.session.add(product)
                db.session.add(log)
                db.session.commit()
                
                flash(f'تم إضافة المنتج {product.name} بنجاح', 'success')
                app.logger.debug(f"Added new product {product.name}")
            
            return redirect(url_for('inventory.index'))
            
        except Exception as e:
            # Log any errors that occur
            app.logger.error(f"Error in add_new_product: {str(e)}")
            import traceback
            app.logger.error(traceback.format_exc())
            flash(f'حدث خطأ أثناء إضافة المنتج: {str(e)}', 'danger')
            return render_template('inventory/add_new.html')
    
    return render_template('inventory/add_new.html')


@inventory_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    form = ProductForm()
    app.logger.debug(f"Request method: {request.method}")
    
    if request.method == 'POST':
        app.logger.debug(f"Form data: {request.form}")
        app.logger.debug(f"Form validation: {form.validate()}")
        if not form.validate():
            app.logger.debug(f"Form errors: {form.errors}")
    
    if form.validate_on_submit():
        app.logger.debug("Form validated successfully")
        # Check if product with same name, color, and material exists
        existing_product = Product.query.filter_by(
            name=form.name.data,
            color=form.color.data,
            material=form.material.data,
            type=form.type.data
        ).first()
        
        if existing_product:
            # Update existing product
            existing_product.quantity += form.quantity.data
            existing_product.finishing_cost = form.finishing_cost.data
            
            if form.type.data == 'Printed':
                existing_product.printing_cost = form.printing_cost.data
            
            # Log the update
            log = SystemLog(
                action='product_update',
                details=f'تحديث المنتج: {existing_product.name} ({existing_product.color})',
                user_id=current_user.id
            )
            
            db.session.add(log)
            db.session.commit()
            
            flash(f'تم تحديث المنتج {existing_product.name} بنجاح', 'success')
            app.logger.debug(f"Updated product {existing_product.name}")
        else:
            # Create new product
            product = Product(
                name=form.name.data,
                color=form.color.data,
                material=form.material.data,
                quantity=form.quantity.data,
                type=form.type.data,
                finishing_cost=form.finishing_cost.data,
                printing_cost=form.printing_cost.data if form.type.data == 'Printed' else 0
            )
            
            # Log the creation
            log = SystemLog(
                action='product_create',
                details=f'إنشاء منتج جديد: {product.name} ({product.color})',
                user_id=current_user.id
            )
            
            db.session.add(product)
            db.session.add(log)
            db.session.commit()
            
            flash(f'تم إضافة المنتج {product.name} بنجاح', 'success')
            app.logger.debug(f"Added new product {product.name}")
        
        return redirect(url_for('inventory.index'))
    
    return render_template('inventory/add.html', form=form)


@inventory_bp.route('/view/<int:product_id>')
@login_required
def view(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Get all invoices that contain this product
    invoices = []
    for item in product.invoice_items:
        if item.invoice not in invoices:
            invoices.append(item.invoice)
    
    # Sort invoices by date
    invoices.sort(key=lambda x: x.date, reverse=True)
    
    # Create delete form
    delete_product_form = DeleteProductForm()
    
    return render_template(
        'inventory/view.html',
        product=product,
        invoices=invoices,
        delete_product_form=delete_product_form
    )


@inventory_bp.route('/delete/<int:product_id>', methods=['POST'])
@login_required
@admin_required
def delete(product_id):
    form = DeleteProductForm()
    if not form.validate_on_submit():
        flash('خطأ في التحقق من صحة النموذج', 'danger')
        return redirect(url_for('inventory.view', product_id=product_id))

    product = Product.query.get_or_404(product_id)
    
    # Check if product has been used in any invoices
    invoice_items_count = len(product.invoice_items)
    
    # Check if product has been used in any invoices
    if invoice_items_count > 0:
        flash(f'لا يمكن حذف المنتج لأنه مستخدم في {invoice_items_count} فاتورة', 'danger')
        return redirect(url_for('inventory.view', product_id=product.id))
    
    # Log the deletion
    log = SystemLog(
        action='product_delete',
        details=f'حذف المنتج: {product.name} ({product.color})',
        user_id=current_user.id
    )
    
    db.session.add(log)
    db.session.delete(product)  # This will cascade delete all related records
    db.session.commit()
    
    flash(f'تم حذف المنتج {product.name} بنجاح', 'success')
    return redirect(url_for('inventory.index'))

@inventory_bp.route('/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit(product_id):
    product = Product.query.get_or_404(product_id)
    form = ProductForm(obj=product)
    
    if form.validate_on_submit():
        # Update product details
        product.name = form.name.data
        product.color = form.color.data
        product.material = form.material.data
        product.quantity = form.quantity.data
        product.type = form.type.data
        product.finishing_cost = form.finishing_cost.data
        
        if form.type.data == 'Printed':
            product.printing_cost = form.printing_cost.data
        else:
            product.printing_cost = 0
        
        # Log the update
        log = SystemLog(
            action='product_edit',
            details=f'تعديل المنتج: {product.name} ({product.color})',
            user_id=current_user.id
        )
        
        db.session.add(log)
        db.session.commit()
        
        flash(f'تم تحديث المنتج {product.name} بنجاح', 'success')
        return redirect(url_for('inventory.view', product_id=product.id))
    
    return render_template('inventory/edit.html', form=form, product=product)


@inventory_bp.route('/merge_products', methods=['POST'])
@login_required
@admin_required
def merge_products():
    form = MergeProductsForm()
    if not form.validate_on_submit():
        flash('خطأ في التحقق من صحة النموذج', 'danger')
        return redirect(url_for('inventory.index'))
    try:
        # Get product IDs from form and convert to integers
        product_ids = [int(id) for id in request.form.getlist('product_ids[]')]
        target_product_id = int(request.form.get('target_product_id'))
        
        if not product_ids or not target_product_id or target_product_id not in product_ids:
            flash('يجب اختيار المنتجات للدمج والمنتج الهدف', 'danger')
            return redirect(url_for('inventory.index'))
    except (ValueError, TypeError):
        flash('حدث خطأ في معالجة البيانات', 'danger')
        return redirect(url_for('inventory.index'))
    
    # Get target product
    target_product = Product.query.get_or_404(target_product_id)
    
    # Process each product to merge
    for product_id in product_ids:
        if product_id == target_product_id:
            continue
            
        product = Product.query.get(product_id)
        if not product:
            continue
            
        # Add quantities
        target_product.quantity += product.quantity
        
        # Update invoice items to point to target product
        for item in product.invoice_items:
            item.product_id = target_product.id
        
        # Log the merge
        log = SystemLog(
            action='product_merge',
            details=f'تم دمج المنتج {product.name} ({product.color}) مع {target_product.name} ({target_product.color})',
            user_id=current_user.id
        )
        db.session.add(log)
        
        # Delete the merged product
        db.session.delete(product)
    
    db.session.commit()
    flash('تم دمج المنتجات بنجاح', 'success')
    return redirect(url_for('inventory.index'))
