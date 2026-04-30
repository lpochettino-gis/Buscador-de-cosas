import json
from pathlib import Path


TARGET_NB = Path("BUSCADOR_DE_COSAS_MEJORADO.ipynb")
COMPAT_NB = Path("buscador_visual_oficina_tecnica_colab.ipynb")
MODULE_PATH = Path("buscador_visual_oficina_tecnica.py")


def src(text: str) -> list[str]:
    text = text.strip("\n")
    return [line + "\n" for line in text.splitlines()]


intro_md = r"""
# Buscador Visual para Oficina Tecnica y SyH

Herramienta para revisar muchas fotos de obra, ductos o frente de trabajo y generar un paquete de reporte con:

- Busqueda simultanea de varios objetos: por ejemplo `cono, cartel, casco, autos`.
- Perfil rapido, equilibrado o profundo. El modo profundo hace tres pasadas sobre la imagen para mejorar objetos chicos o fotos de dron.
- Imagenes marcadas con cajas y etiquetas.
- PDF ejecutivo con resumen, matriz de encuentros y anexo fotografico.
- Excel con hoja `Encuentros`, donde cada hallazgo aparece contado al lado.
- CSV de detalle y ZIP final para entregar.

La IA ayuda a acelerar el relevamiento, pero no reemplaza la validacion de oficina tecnica, inspeccion de obra o Higiene y Seguridad.
"""


install_md = r"""
## 1. Instalar dependencias

Ejecuta esta celda una vez por sesion de Colab.
"""


install_code = r"""
!pip -q install ultralytics opencv-python pillow reportlab pandas openpyxl ipywidgets tqdm
"""


tool_md = r"""
## 2. Cargar motor de inspeccion

Ejecuta esta celda completa. Define catalogo, busqueda multiobjeto, reportes y exportables.
"""


run_md = r"""
## 3. Configurar y ejecutar

Selecciona objetivos, sube fotos y ejecuta el analisis.
"""


ui_code = r"""
from pathlib import Path
import os
import shutil

import ipywidgets as widgets
from IPython.display import clear_output, display

try:
    from google.colab import files
except Exception:
    files = None


INPUT_DIR = Path("/content/input_fotos_relevamiento")
OUTPUT_DIR = Path("/content/reporte_visual_oficina_tecnica")

if INPUT_DIR.exists():
    shutil.rmtree(INPUT_DIR)
if OUTPUT_DIR.exists():
    shutil.rmtree(OUTPUT_DIR)
INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


catalog_options = [(f"{target.label} | {target.group}", target.label) for target in CATALOG]
default_values = tuple(label for label in DEFAULT_PRESET_LABELS if label in {target.label for target in CATALOG})

selector_objetivos = widgets.SelectMultiple(
    options=catalog_options,
    value=default_values,
    description="Catalogo",
    layout=widgets.Layout(width="98%", height="210px"),
)

texto_extra = widgets.Textarea(
    value="cono, cartel, casco, autos",
    placeholder="Ej: cono, cartel, casco, autos, zanja, excavadora",
    description="Extra",
    layout=widgets.Layout(width="98%", height="70px"),
)

perfil = widgets.Dropdown(
    options=[
        ("Rapido - 1 pasada general", "rapida"),
        ("Equilibrado - general + tiles", "equilibrada"),
        ("Profundo x3 - general + dos grillas", "profunda"),
    ],
    value="equilibrada",
    description="Perfil",
    layout=widgets.Layout(width="98%"),
)

confianza = widgets.FloatSlider(
    value=0.08,
    min=0.01,
    max=0.50,
    step=0.01,
    readout_format=".2f",
    description="Conf.",
    layout=widgets.Layout(width="98%"),
)

batch_size = widgets.IntSlider(
    value=8,
    min=1,
    max=16,
    step=1,
    description="Lote",
    layout=widgets.Layout(width="98%"),
)

modelo = widgets.Dropdown(
    options=[
        ("YOLO-World small - recomendado", "yolov8s-world.pt"),
        ("YOLO-World medium - mas pesado", "yolov8m-world.pt"),
        ("YOLO-World large - solo GPU holgada", "yolov8l-world.pt"),
    ],
    value="yolov8s-world.pt",
    description="Modelo",
    layout=widgets.Layout(width="98%"),
)

boton_subir = widgets.Button(description="Subir fotos", button_style="info")
boton_ejecutar = widgets.Button(description="Procesar y generar reporte", button_style="success")
boton_descargar_zip = widgets.Button(description="Descargar ZIP", button_style="warning", disabled=True)
boton_descargar_pdf = widgets.Button(description="Descargar PDF", button_style="danger", disabled=True)
boton_descargar_excel = widgets.Button(description="Descargar Excel", button_style="primary", disabled=True)

salida = widgets.Output()
artefactos_generados = {}


def subir_fotos(_):
    with salida:
        clear_output()
        if files is None:
            print(f"No estoy en Colab. Copia tus fotos manualmente en: {INPUT_DIR}")
            return
        uploaded = files.upload()
        copy_uploaded_files(uploaded, INPUT_DIR)
        total = len(image_files(INPUT_DIR))
        print(f"Fotos listas para procesar: {total}")


def ejecutar(_):
    global artefactos_generados
    with salida:
        clear_output()
        if len(image_files(INPUT_DIR)) == 0:
            print("Primero subi fotos o copia imagenes en la carpeta de entrada.")
            return

        seleccion = list(selector_objetivos.value)
        extra = texto_extra.value
        targets = build_targets(preset_labels=seleccion, extra_terms=extra)
        print("Objetivos finales:")
        for target in targets:
            print(f" - {target.label} -> {target.prompt} [{target.group}]")
        print("")

        inspector = VisualInspectionTool(
            input_folder=INPUT_DIR,
            output_folder=OUTPUT_DIR,
            targets=targets,
            confidence=confianza.value,
            search_profile=perfil.value,
            batch_size=batch_size.value,
            model_name=modelo.value,
        )
        inspector.process()
        artefactos_generados = inspector.export_all()

        print("")
        print("Reporte generado:")
        for nombre, ruta in artefactos_generados.items():
            print(f" - {nombre}: {ruta}")

        boton_descargar_zip.disabled = False
        boton_descargar_pdf.disabled = False
        boton_descargar_excel.disabled = False


def descargar(nombre):
    if files is None:
        print(f"Archivo disponible en: {artefactos_generados.get(nombre)}")
        return
    ruta = artefactos_generados.get(nombre)
    if ruta:
        files.download(str(ruta))


boton_subir.on_click(subir_fotos)
boton_ejecutar.on_click(ejecutar)
boton_descargar_zip.on_click(lambda _: descargar("zip"))
boton_descargar_pdf.on_click(lambda _: descargar("pdf"))
boton_descargar_excel.on_click(lambda _: descargar("excel"))

display(selector_objetivos, texto_extra, perfil, confianza, batch_size, modelo)
display(widgets.HBox([boton_subir, boton_ejecutar]))
display(widgets.HBox([boton_descargar_zip, boton_descargar_pdf, boton_descargar_excel]))
display(salida)
"""


tips_md = r"""
## 4. Criterios de uso en obra

- Para recorridas a pie, empieza con perfil `Equilibrado` y confianza `0.08` a `0.15`.
- Para fotos de dron, usa `Profundo x3` si los objetos son chicos.
- Si aparecen falsos positivos, sube la confianza o cambia a objetivos mas especificos.
- Si faltan objetos, baja la confianza y agrega sinonimos en ingles en el campo extra.
- El Excel tiene la hoja `Encuentros`: hallazgo, cantidad, fotos donde aparece, confianza y recomendacion.
- El PDF sirve para lectura ejecutiva y el ZIP para adjuntar todo el paquete.
"""


def build_notebook() -> dict:
    module_source = MODULE_PATH.read_text(encoding="utf-8")
    cells = [
        {"cell_type": "markdown", "metadata": {}, "source": src(intro_md)},
        {"cell_type": "markdown", "metadata": {}, "source": src(install_md)},
        {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": src(install_code)},
        {"cell_type": "markdown", "metadata": {}, "source": src(tool_md)},
        {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": src(module_source)},
        {"cell_type": "markdown", "metadata": {}, "source": src(run_md)},
        {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": src(ui_code)},
        {"cell_type": "markdown", "metadata": {}, "source": src(tips_md)},
    ]
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
            "colab": {"name": TARGET_NB.name, "provenance": []},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    notebook = build_notebook()
    TARGET_NB.write_text(json.dumps(notebook, ensure_ascii=False, indent=2), encoding="utf-8")
    COMPAT_NB.write_text(json.dumps(notebook, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Notebook generado: {TARGET_NB}")
    print(f"Copia compatible generada: {COMPAT_NB}")


if __name__ == "__main__":
    main()
