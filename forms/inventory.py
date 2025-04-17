from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SelectField, FloatField, SubmitField, FieldList, HiddenField
from wtforms.validators import DataRequired, NumberRange


class ProductForm(FlaskForm):
    name = StringField('اسم المنتج', validators=[DataRequired()])
    color = StringField('اللون', validators=[DataRequired()])
    material = StringField('المادة', validators=[DataRequired()])
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=0)])
    type = SelectField('النوع', choices=[
        ('Plain', 'عادي'),
        ('Printed', 'مطبوع')
    ], validators=[DataRequired()])
    finishing_cost = FloatField('تكلفة التشطيب', validators=[DataRequired(), NumberRange(min=0)])
    printing_cost = FloatField('تكلفة الطباعة', validators=[NumberRange(min=0)])
    submit = SubmitField('إضافة منتج')


class DeleteProductForm(FlaskForm):
    submit = SubmitField('تأكيد الحذف')


class MergeProductsForm(FlaskForm):
    product_ids = FieldList(HiddenField('Product ID'))
    target_product_id = HiddenField('Target Product ID')
    submit = SubmitField('دمج المنتجات')
