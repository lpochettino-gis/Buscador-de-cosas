# Buscador Visual para Oficina Tecnica y SyH

Herramienta para procesar multiples fotos de obra, ductos o frentes de trabajo y generar un paquete de reporte.

## Que entrega

- `reporte_inspeccion_visual.pdf`: resumen ejecutivo, matriz de encuentros, detalle por foto y anexo fotografico.
- `reporte_inspeccion_visual.xlsx`: incluye hoja `Encuentros` con cada hallazgo y su cantidad al lado.
- `tablas/*.csv`: detalle de detecciones, resumen por foto y resumen de encuentros.
- `imagenes_marcadas/*.jpg`: fotos con cajas, etiquetas y confianza.
- `paquete_reporte_visual.zip`: paquete listo para compartir.

## Busqueda multiobjeto

Se cargan todos los objetivos en una sola configuracion de YOLO-World. Asi se pueden buscar, por ejemplo:

```text
cono, cartel, casco, autos
```

La herramienta traduce terminos comunes de obra en castellano a prompts utiles en ingles cuando corresponde: `cono -> traffic cone`, `cartel -> safety sign`, `casco -> hard hat`, `autos -> car`.

## Perfiles de busqueda

- `rapida`: una pasada general. Util para pruebas o fotos cercanas.
- `equilibrada`: pasada general + grilla por sectores. Es el valor recomendado.
- `profunda`: tres pasadas, pensada para fotos de dron o elementos chicos. Tarda mas, pero encuentra mejor.

Todas las pasadas se deduplican con NMS por clase para evitar contar tres veces el mismo objeto.

## Uso en Colab

1. Abre `BUSCADOR_DE_COSAS_MEJORADO.ipynb`.
2. Ejecuta la instalacion.
3. Ejecuta la celda del motor.
4. Selecciona objetivos, sube fotos y procesa.
5. Descarga el ZIP, PDF o Excel.

## Uso local

```powershell
pip install ultralytics opencv-python pillow reportlab pandas openpyxl
python buscador_visual_oficina_tecnica.py --input "C:\ruta\a\fotos" --output "C:\ruta\a\salida" --buscar "cono, cartel, casco, autos" --perfil equilibrada
```

## Criterio tecnico

El reporte esta armado para oficina tecnica y Seguridad e Higiene: separa EPP, senalizacion, vehiculos, maquinaria, ductos, excavaciones, trabajo en altura y orden/limpieza.

Sirve como preclasificacion y trazabilidad fotografica. No reemplaza la inspeccion de un profesional habilitado ni emite conformidad legal automatica.
