from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Categorías de regla salarial que componen cada grupo. Se comparan por código y
# no por nombre, que es traducible.
CAT_REMUNERATIVO = 'GROSS'
CAT_NO_REM = 'HABER_NR'
CAT_RET_SS = ('RET_SS',)
CAT_RET_OS = ('RET_OS',)
CAT_RET_SIND = ('RET_SIND',)
CAT_NETO = 'NET'


class PayrollControlF931(models.Model):
    """Control de una liquidación contra el F.931, del modo en que se venía haciendo.

    Reemplaza la planilla de Excel con la que se controla el formulario antes de
    presentarlo: mismos números, mismos cortes, misma lógica, pero calculados
    desde los recibos en vez de exportados a mano.

    El control es un registro por **período**, no por liquidación: el F.931 se
    presenta uno por mes y agrupa todo lo que se liquidó —el mensual, el
    aguinaldo y las bajas—. En junio de 2026, por ejemplo, fueron cuatro
    liquidaciones en un solo formulario.

    Los valores del formulario se cargan a mano, mirando la pantalla de ARCA. Es
    a propósito: si se leyeran del propio sistema se estaría comparando Odoo
    contra Odoo, y el control dejaría de detectar un error de cálculo.
    """
    _name = 'payroll.control.f931'
    _description = 'Control de liquidación contra el F.931'
    # el chatter deja asentado quién marcó el control como presentado y cuándo,
    # que en una declaración jurada es parte del control mismo
    _inherit = ['mail.thread']
    _order = 'anio desc, mes desc'
    _rec_name = 'display_name'

    MESES = [('01', 'Enero'), ('02', 'Febrero'), ('03', 'Marzo'), ('04', 'Abril'),
             ('05', 'Mayo'), ('06', 'Junio'), ('07', 'Julio'), ('08', 'Agosto'),
             ('09', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'),
             ('12', 'Diciembre')]

    mes = fields.Selection(MESES, 'Mes', required=True,
                           default=lambda s: fields.Date.today().strftime('%m'))
    anio = fields.Integer('Año', required=True,
                          default=lambda s: fields.Date.today().year)
    company_id = fields.Many2one('res.company', 'Empresa', required=True,
                                 default=lambda s: s.env.company)
    state = fields.Selection(
        [('draft', 'En control'), ('done', 'Presentado')],
        'Estado', default='draft', required=True, tracking=True,
    )
    payslip_run_ids = fields.Many2many(
        'hr.payslip.run', string='Liquidaciones del período',
        help='Todas las liquidaciones que entran en este F.931: la mensual, el '
             'aguinaldo y las bajas. Si se deja vacío se toman todas las del '
             'período al recalcular.',
    )
    nota = fields.Text('Observaciones')

    # ── Lo que dice el sistema ────────────────────────────────────────────────
    remuneraciones = fields.Monetary('Remuneraciones', compute='_compute_totales',
                                     currency_field='currency_id')
    no_remunerativo = fields.Monetary('No remunerativo', compute='_compute_totales',
                                      currency_field='currency_id')
    aportes_ss = fields.Monetary('Aportes de seguridad social',
                                 compute='_compute_totales', currency_field='currency_id',
                                 help='Jubilación y Ley 19.032. Es el código 301 del F.931.')
    aportes_os = fields.Monetary('Aportes de obra social', compute='_compute_totales',
                                 currency_field='currency_id',
                                 help='Es el código 302 del F.931.')
    aportes_total = fields.Monetary('Total de aportes', compute='_compute_totales',
                                    currency_field='currency_id')
    retenciones = fields.Monetary('Total de retenciones', compute='_compute_totales',
                                  currency_field='currency_id',
                                  help='Incluye además la cuota sindical y el seguro de vida.')
    neto = fields.Monetary('Neto a pagar', compute='_compute_totales',
                           currency_field='currency_id')
    empleados = fields.Integer('Empleados', compute='_compute_totales')

    # ── Lo que dice el formulario (se carga a mano) ───────────────────────────
    f931_remuneraciones = fields.Monetary(
        'Remuneraciones del F.931', currency_field='currency_id',
        help='La "Suma de Rem. 1" del formulario.')
    f931_301 = fields.Monetary(
        '301 - Aportes de seguridad social', currency_field='currency_id')
    f931_302 = fields.Monetary(
        '302 - Aportes de obra social', currency_field='currency_id')
    f931_empleados = fields.Integer('Empleados en nómina según el F.931')

    # ── Las diferencias ───────────────────────────────────────────────────────
    dif_remuneraciones = fields.Monetary('Diferencia', compute='_compute_diferencias',
                                         currency_field='currency_id')
    dif_aportes = fields.Monetary('Diferencia ', compute='_compute_diferencias',
                                  currency_field='currency_id')
    dif_empleados = fields.Integer('Diferencia  ', compute='_compute_diferencias')
    cuadra = fields.Boolean('Cuadra', compute='_compute_diferencias',
                            help='Verdadero cuando ninguna diferencia supera un peso.')
    resumen = fields.Char('Resultado del control', compute='_compute_diferencias')

    currency_id = fields.Many2one('res.currency', compute='_compute_currency')

    linea_empleado_ids = fields.One2many(
        'payroll.control.f931.empleado', 'control_id', 'Por empleado', readonly=True)
    linea_concepto_ids = fields.One2many(
        'payroll.control.f931.concepto', 'control_id', 'Por concepto', readonly=True)
    linea_boleta_ids = fields.One2many(
        'payroll.control.f931.boleta', 'control_id', 'Boletas', readonly=True)

    _sql_constraints = [
        ('periodo_uniq', 'unique(mes, anio, company_id)',
         'Ya existe un control para ese período.'),
    ]

    @api.depends('company_id')
    def _compute_currency(self):
        for c in self:
            c.currency_id = c.company_id.currency_id

    @api.depends('mes', 'anio')
    def _compute_display_name(self):
        for c in self:
            etiqueta = dict(self.MESES).get(c.mes, c.mes or '')
            c.display_name = f'Control F.931 — {etiqueta} {c.anio or ""}'.strip()

    # ── Cálculo ───────────────────────────────────────────────────────────────
    def _recibos(self):
        """Los recibos del período. Los cancelados quedan afuera: suman sin avisar."""
        self.ensure_one()
        if self.payslip_run_ids:
            dominio = [('payslip_run_id', 'in', self.payslip_run_ids.ids)]
        else:
            desde = f'{self.anio}-{self.mes}-01'
            hasta = fields.Date.end_of(fields.Date.to_date(desde), 'month')
            dominio = [('date_from', '>=', desde), ('date_from', '<=', hasta)]
        dominio += [('state', '!=', 'cancel'),
                    ('company_id', '=', self.company_id.id)]
        return self.env['hr.payslip'].search(dominio)

    @api.depends('mes', 'anio', 'payslip_run_ids', 'company_id')
    def _compute_totales(self):
        for c in self:
            recibos = c._recibos()
            lineas = recibos.mapped('line_ids')
            def suma(codigos):
                return sum(lineas.filtered(
                    lambda l: l.salary_rule_id.category_id.code in codigos).mapped('total'))
            c.remuneraciones = suma((CAT_REMUNERATIVO,))
            c.no_remunerativo = suma((CAT_NO_REM,))
            c.aportes_ss = abs(suma(CAT_RET_SS))
            c.aportes_os = abs(suma(CAT_RET_OS))
            c.aportes_total = c.aportes_ss + c.aportes_os
            c.retenciones = abs(suma(CAT_RET_SS + CAT_RET_OS + CAT_RET_SIND + ('DED',)))
            c.neto = suma((CAT_NETO,))
            c.empleados = len(recibos.mapped('employee_id'))

    @api.depends('remuneraciones', 'aportes_total', 'empleados',
                 'f931_remuneraciones', 'f931_301', 'f931_302', 'f931_empleados')
    def _compute_diferencias(self):
        for c in self:
            c.dif_remuneraciones = c.remuneraciones - c.f931_remuneraciones
            c.dif_aportes = c.aportes_total - (c.f931_301 + c.f931_302)
            c.dif_empleados = c.empleados - c.f931_empleados
            cargado = any([c.f931_remuneraciones, c.f931_301, c.f931_302])
            # un peso de tolerancia: el formulario redondea y la planilla también
            ok = (abs(c.dif_remuneraciones) < 1 and abs(c.dif_aportes) < 1
                  and c.dif_empleados == 0)
            c.cuadra = bool(cargado and ok)
            if not cargado:
                c.resumen = 'Falta cargar los valores del F.931'
            elif ok:
                c.resumen = 'Cuadra'
            else:
                motivos = []
                if abs(c.dif_remuneraciones) >= 1:
                    motivos.append(f'remuneraciones {c.dif_remuneraciones:,.2f}')
                if abs(c.dif_aportes) >= 1:
                    motivos.append(f'aportes {c.dif_aportes:,.2f}')
                if c.dif_empleados:
                    motivos.append(f'{abs(c.dif_empleados)} empleado(s) de '
                                   f'{"más" if c.dif_empleados > 0 else "menos"}')
                c.resumen = 'No cuadra: ' + ' · '.join(motivos)

    def action_recalcular(self):
        """Rearma el detalle: por empleado, por concepto y las boletas."""
        for c in self:
            c.linea_empleado_ids.unlink()
            c.linea_concepto_ids.unlink()
            c.linea_boleta_ids.unlink()
            recibos = c._recibos()
            if not recibos:
                raise UserError(_('No hay recibos en %s. Verificá el período o '
                                  'elegí las liquidaciones a mano.') % c.display_name)
            c._armar_por_empleado(recibos)
            c._armar_por_concepto(recibos)
            c._armar_boletas(recibos)
        return True

    def _armar_por_empleado(self, recibos):
        """Un renglón por persona, como la hoja de totales de la planilla."""
        self.ensure_one()
        datos = {}
        for recibo in recibos:
            emp = recibo.employee_id
            d = datos.setdefault(emp.id, {
                'employee_id': emp.id, 'control_id': self.id,
                'remunerativo': 0.0, 'no_remunerativo': 0.0,
                'retenciones': 0.0, 'neto': 0.0,
            })
            for linea in recibo.line_ids:
                cod = linea.salary_rule_id.category_id.code
                if cod == CAT_REMUNERATIVO:
                    d['remunerativo'] += linea.total
                elif cod == CAT_NO_REM:
                    d['no_remunerativo'] += linea.total
                elif cod in CAT_RET_SS + CAT_RET_OS + CAT_RET_SIND + ('DED',):
                    d['retenciones'] += abs(linea.total)
                elif cod == CAT_NETO:
                    d['neto'] += linea.total
        self.env['payroll.control.f931.empleado'].create(list(datos.values()))

    def _armar_por_concepto(self, recibos):
        """Un renglón por concepto de aporte: jubilación, PAMI y cada obra social.

        Es el corte con el que se cierra contra los códigos 301 y 302, así que
        se separa lo que va a cada uno.
        """
        self.ensure_one()
        datos = {}
        for linea in recibos.mapped('line_ids'):
            cod = linea.salary_rule_id.category_id.code
            if cod not in CAT_RET_SS + CAT_RET_OS:
                continue
            clave = (linea.name, cod)
            d = datos.setdefault(clave, {
                'control_id': self.id, 'name': linea.name,
                'destino': '301' if cod in CAT_RET_SS else '302',
                'importe': 0.0, 'cantidad': 0,
            })
            d['importe'] += abs(linea.total)
            d['cantidad'] += 1
        self.env['payroll.control.f931.concepto'].create(list(datos.values()))

    def _armar_boletas(self, recibos):
        """Cuota sindical y seguro de vida, agrupados por convenio.

        Es lo que hace falta para cargar cada boleta en la página del sindicato,
        y por eso van separados: cada convenio se paga por su lado.
        """
        self.ensure_one()
        datos = {}
        for recibo in recibos:
            convenio = recibo.contract_id.structure_type_id
            for linea in recibo.line_ids:
                if linea.salary_rule_id.category_id.code not in CAT_RET_SIND:
                    continue
                clave = (convenio.id, linea.name)
                d = datos.setdefault(clave, {
                    'control_id': self.id, 'name': linea.name,
                    'structure_type_id': convenio.id or False,
                    'importe': 0.0, 'cantidad': 0,
                })
                d['importe'] += abs(linea.total)
                d['cantidad'] += 1
        self.env['payroll.control.f931.boleta'].create(list(datos.values()))

    def action_marcar_presentado(self):
        """Cierra el control. Si no cuadra, exige que la diferencia esté explicada.

        No alcanza con negarse: hay períodos que legítimamente no cuadran y se
        presentan igual —una diferencia conocida, un concepto que se declara por
        otra vía—. Lo que no puede pasar es que se cierren en silencio, así que
        la salida es dejar la explicación escrita en Observaciones, que queda en
        el registro y en el chatter.
        """
        for c in self:
            if not c.cuadra and not (c.nota or '').strip():
                raise UserError(_(
                    'El control no cuadra: %s.\n\nSi la diferencia está explicada, '
                    'dejala anotada en Observaciones antes de marcarlo como '
                    'presentado.') % c.resumen)
            if not c.cuadra:
                c.message_post(body=_(
                    'Marcado como presentado <b>sin cuadrar</b>: %s.<br/>'
                    'Explicación registrada: %s'
                ) % (c.resumen, c.nota))
            c.state = 'done'

    def action_volver_a_control(self):
        self.state = 'draft'


class PayrollControlF931Empleado(models.Model):
    _name = 'payroll.control.f931.empleado'
    _description = 'Control F.931 — detalle por empleado'
    _order = 'employee_id'

    control_id = fields.Many2one('payroll.control.f931', required=True,
                                 ondelete='cascade', index=True)
    employee_id = fields.Many2one('hr.employee', 'Empleado', required=True)
    legajo = fields.Char('Legajo', related='employee_id.barcode', readonly=True)
    remunerativo = fields.Monetary('Haberes', currency_field='currency_id')
    no_remunerativo = fields.Monetary('No remunerativo', currency_field='currency_id')
    retenciones = fields.Monetary('Retenciones', currency_field='currency_id')
    neto = fields.Monetary('Neto', currency_field='currency_id')
    currency_id = fields.Many2one(related='control_id.currency_id')


class PayrollControlF931Concepto(models.Model):
    _name = 'payroll.control.f931.concepto'
    _description = 'Control F.931 — detalle por concepto de aporte'
    _order = 'destino, name'

    control_id = fields.Many2one('payroll.control.f931', required=True,
                                 ondelete='cascade', index=True)
    name = fields.Char('Concepto', required=True)
    destino = fields.Selection(
        [('301', '301 - Seguridad social'), ('302', '302 - Obra social')],
        'Va al código', required=True)
    cantidad = fields.Integer('Recibos')
    importe = fields.Monetary('Importe', currency_field='currency_id')
    currency_id = fields.Many2one(related='control_id.currency_id')


class PayrollControlF931Boleta(models.Model):
    _name = 'payroll.control.f931.boleta'
    _description = 'Control F.931 — boletas de sindicato y seguro de vida'
    _order = 'structure_type_id, name'

    control_id = fields.Many2one('payroll.control.f931', required=True,
                                 ondelete='cascade', index=True)
    name = fields.Char('Concepto', required=True)
    structure_type_id = fields.Many2one('hr.payroll.structure.type', 'Convenio')
    cantidad = fields.Integer('Empleados')
    importe = fields.Monetary('Importe', currency_field='currency_id')
    currency_id = fields.Many2one(related='control_id.currency_id')
