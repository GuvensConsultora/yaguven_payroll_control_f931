# Control del F.931

Módulo Odoo 18 que lleva adentro del sistema el control con el que se verifica una
liquidación de sueldos antes de presentar el F.931.

Reemplaza la planilla de Excel con la que ese control se venía haciendo a mano:
mismos números y mismos cortes, pero calculados desde los recibos.

## Qué hace

Se elige el período, se aprieta **Recalcular** y se comparan tres cosas contra el
formulario: las **remuneraciones**, los **aportes** (códigos 301 y 302) y la
**cantidad de empleados**.

El detalle se abre en tres pestañas:

- **Por empleado** — haberes, retenciones, no remunerativo y neto.
- **Por concepto de aporte** — con el código 301 o 302 al que va cada uno, que es
  el corte con el que se cierra contra el formulario.
- **Boletas** — cuota sindical y seguro de vida, separadas por convenio, que es
  como se pagan.

## Decisiones de diseño

**Los valores del F.931 se cargan a mano.** Si se tomaran del propio sistema se
estaría comparando Odoo contra Odoo, y el control dejaría de detectar un error de
cálculo. Son tres números por mes.

**Un registro por período, no por liquidación.** El F.931 se presenta uno por mes
y agrupa todo lo que se liquidó: el mensual, el aguinaldo y las bajas.

**Los recibos cancelados quedan afuera.** Suman a los totales sin que se note
desde ninguna pantalla.

**Tolerancia de un peso** en las diferencias: el formulario redondea, y exigir
cero sería exigir algo que la propia presentación no cumple.

**No deja marcar como presentado si no cuadra**, salvo que la diferencia quede
anotada en las observaciones.

## Instalación

Depende de `hr_payroll` y de `payroll_ar_reform_27802` (por las categorías de
regla salarial `RET_SS`, `RET_OS` y `HABER_NR`, que son las que separan los
aportes por destino).

Menú: **Nómina › Reportes › Control del F.931**

---
Yagüven C.G. · [yaguven.com](https://yaguven.com) · Odoo Partner
