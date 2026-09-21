# Corrección del buscador agro para fotos comunes

Fecha: 2026-09-21. Se reprodujo la omisión de fotos sencillas con la configuración anterior y se probó la corrección con modelos reales.

## Actualización de instalación: error `GenerationMixin`

Se añadió una celda de instalación con comprobación de importaciones en un proceso limpio y reparación dirigida de Transformers y sus dependencias directas. Ahora se fija también tokenizers 0.22.2, huggingface-hub 0.36.2 y safetensors 0.8.0. Se comprueban `GenerationMixin` y el modelo Grounding DINO concreto sin descargar pesos. Si quedaron librerías antiguas en memoria, se exige reinicio antes de inferir. Un fallo persistente conserva el traceback para identificar la dependencia real; no se atribuye automáticamente a la imagen o a Python 3.13.

**Uso después de actualizar:** reiniciar la sesión, ejecutar la celda 1 y esperar la comprobación. Si pide otro reinicio, hacerlo y continuar desde **2. Motor**, configuración e interfaz, sin reinstalar. Se probaron cinco regresiones del instalador además de las 24 pruebas existentes. La comprobación real de importación pasó en el entorno aislado Python 3.12; la sesión remota del usuario con Python 3.13 no está disponible para reproducir su estado exacto.

También se ejecutó una reinstalación real de esos cuatro paquetes con NumPy previamente cargado: la comprobación terminó correctamente y se verificó el bloqueo hasta reiniciar la sesión.

## Cambio

- Grounding DINO Tiny reemplaza a YOLO-World como motor predeterminado del agro. Revisión fijada: `a2bb814dd30d776dcf7e30523b00659f4f141c71`; Transformers 4.57.3; confianza 0.25.
- Automático analiza las fotos completas, con lado máximo de 960 px. Las cajas se convierten a coordenadas de la imagen original. El modo detallado añade sectores para objetos pequeños.
- GeoTIFF con CRS conserva ventanas a resolución original. Se puede elegir ese modo manualmente para mosaicos JPG o TIFF sin CRS.
- Se mantienen carga directa, JPG/PNG y otros formatos habituales, ZIP/7z y exportaciones. No se necesita Drive.
- Las clases se asignan por el token de mayor puntuación, con correspondencia explícita al objetivo solicitado. Se mantienen flores y plantas como contexto y se excluyen de la salida las clases no seleccionadas.

## Diagnóstico observado

Se usaron las primeras dos entradas del archivo público de TensorFlow para cuatro categorías de flores: siete fotografías y una ilustración. Se añadieron dos fotos de plantas sin flores de SARE/Cornell y una escena urbana de Ultralytics. Las fotos tienen distintas dimensiones y encuadres; incluyen primeros planos cortados, ramos, cabezas con semillas y flores pequeñas. No hay cajas de referencia exhaustivas.

| Caso | Configuración anterior | Versión corregida |
|---|---:|---:|
| Foto de flor grande cortada por el borde | 0 flores | 1 flor |
| Foto con dos flores destacadas | 1 flor | 2 flores |
| Foto mirando flores contra el cielo | 0 flores | 10 cajas de flor |
| Dos fotos de cabezas con semillas | 0 en ambas | 1 caja de flor en cada una |
| Dos plantas sin flores | 0 en ambas | 1 planta en cada una, 0 flores |
| Escena urbana de control | 0 | 0 flores; 1 candidato débil de planta en un balcón (score 0.257) |

Los números son **salidas del detector**, no conteos verdaderos ni medidas de precisión. La escena urbana contiene vegetación y no constituye un negativo puro para plantas; su caja débil necesita revisión. Un ramo recibió una sola caja: no se garantiza contar cada flor individual.

La comparación anterior usa YOLO-World small, prompts `flower`/`weed plant`, umbral 0.20 y sectores de 640 px. La corregida usa Grounding DINO, `flower`/`plant`, umbral 0.25 y foto completa. También se exploraron YOLO-World mediano y otros prompts, sin una mejora consistente. La línea base por color generó muchos candidatos en objetos urbanos y no se incorporó como detector.

Se ejecutó el notebook generado con inferencia real mediante sus callbacks: cargar una foto y buscar flores, cargar una planta y buscar plantas, y buscar sólo flores sobre esa misma planta. Los tres casos pasaron, incluyendo imagen marcada y ZIP. No se abrió una sesión remota interactiva de Colab.

## Alcance y reproducción

Entorno aislado: Windows, Python 3.12.13, PyTorch 2.8 CPU. Se descargaron y ejecutaron los pesos reales. `diagnostico_resultados.json` conserva scores, cajas, fuentes y hashes; `entorno_diagnostico.txt` registra las dependencias. Los scripts están en la entrega local/ZIP.

```powershell
python diagnostico_fotos.py --prepare --plants
python diagnostico_fotos.py --baseline --probe --dino
python diagnostico_fotos.py --legacy --end-to-end
python verificar_foto_notebook.py
```

Es una comprobación funcional exploratoria sobre 11 imágenes, utilizadas también para seleccionar el método. No hay entrenamiento, separación independiente de prueba, métricas de precisión/recall ni intervalos de confianza. Se desconoce si imágenes públicas formaron parte del preentrenamiento; no se afirma generalización a datos nuevos. No se recibieron las fotos del usuario ni ortomosaicos reales etiquetados.

Una planta detectada **no queda identificada como maleza ni como especie**. Los resultados requieren revisión; pueden omitir objetos, agruparlos o producir falsos positivos. Para evaluar uso agronómico se necesitan ejemplos locales y evaluación por lotes/vuelos independientes.

## Fuentes

- [Documentación oficial de Grounding DINO](https://huggingface.co/docs/transformers/v4.57.3/en/model_doc/grounding-dino).
- [Conjunto público de flores de TensorFlow](https://www.tensorflow.org/tutorials/load_data/images). El archivo descargado incluye `LICENSE.txt` con atribuciones de sus imágenes.
- [Fotografías de plantas SARE/Cornell](https://www.sare.org/publications/manage-weeds-on-your-farm/dandelion/): Antonio DiTommaso y Scott Morris, Cornell University. Se usaron localmente para diagnóstico; no se redistribuyen.
- [Escena urbana de Ultralytics](https://github.com/ultralytics/assets/blob/main/im/bus.jpg).
