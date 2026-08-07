{
    'name': 'Yagüven - Control del F.931',
    'version': '18.0.1.3.0',
    'summary': 'Control de la liquidación contra el F.931, antes de presentarlo',
    'description': '''
Control del F.931
=================

Agrega **Nómina › Reportes › Control del F.931**: la pantalla con la que se
verifica una liquidación antes de presentar el formulario.

Reemplaza la planilla de Excel con la que se venía haciendo ese control: mismos
números y mismos cortes, pero calculados desde los recibos en vez de exportados
a mano.

Cómo funciona
-------------
Se elige el período, se aprieta **Recalcular** y se comparan tres cosas contra
el formulario: las **remuneraciones**, los **aportes** (códigos 301 y 302) y la
**cantidad de empleados**.

Los valores del F.931 **se cargan a mano**, mirando la pantalla de ARCA. Es a
propósito: si se tomaran del propio sistema se estaría comparando Odoo contra
Odoo, y el control dejaría de detectar un error de cálculo.

Un registro **por período**, no por liquidación: el F.931 se presenta uno por mes
y agrupa todo lo que se liquidó — el mensual, el aguinaldo y las bajas.

El detalle
----------
- **Por empleado**: haberes, retenciones, no remunerativo y neto.
- **Por concepto de aporte**, con el código 301 o 302 al que va cada uno. Es el
  corte con el que se cierra contra el formulario.
- **Boletas** de cuota sindical y seguro de vida, separadas por convenio: cada
  una se paga por su lado.

Detalles que evitan errores conocidos
-------------------------------------
- Los **recibos cancelados quedan afuera**: suman a los totales sin que se note.
- **Tolerancia de un peso** en las diferencias: el formulario redondea.
- **No deja marcar como presentado si no cuadra**, salvo que la diferencia quede
  anotada en Observaciones.
''',
    'author': 'Yagüven C.G.',
    'website': 'https://yaguven.com',
    'category': 'Human Resources/Payroll',
    'license': 'LGPL-3',
    'depends': ['mail', 'hr_payroll', 'payroll_ar_reform_27802'],
    'data': [
        'security/ir.model.access.csv',
        'views/payroll_control_f931_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'yaguven_payroll_control_f931/static/src/scss/control_f931.scss',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}
