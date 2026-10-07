# SismoLab AVL

Proyecto de Estructuras de Datos, Universidad de Caldas.

Hicimos un observatorio sísmico simulado. Las estaciones mandan reportes de terremotos y el programa los
organiza en un árbol AVL. El orden del árbol depende de tres cosas, en este orden: la prioridad del evento,
su magnitud y su ID. Los datos son inventados y las reglas de prioridad son las del enunciado; no es un
modelo real de riesgo sísmico.

Además del AVL usamos un BST para comparar (es el mismo árbol pero sin balanceo), una cola para los reportes
que van llegando y una pila para poder deshacer acciones. Todas son implementaciones nuestras, no usamos
librerías de árboles.

## Integrantes

- Matías Vásquez: modelos y servicios (eventos, reportes, prioridad, cola, deshacer).
- Samuel Saldarriaga: estructuras (AVL, BST, comparador de claves) y dibujo de los árboles.
- Manuel Estrada: persistencia JSON, datos de prueba, punto de entrada e interfaz.

## Cómo ejecutarlo

Solo se necesita Python 3.8 o más reciente. No hay que instalar nada más: la ventana está hecha con Tkinter, que ya viene con Python.

En Windows se puede dar doble clic a `iniciar.bat`. Si Windows lo bloquea, o en otro sistema, abran una
terminal en esta carpeta y escriban:

```bash
python main.py
```

Si sale "Falta Tkinter", hay que reinstalar Python desde python.org dejando marcada la opción
"tcl/tk and IDLE" (en Ubuntu: `sudo apt install python3-tk`).

## Pruebas

```bash
python -m unittest discover -s tests -t .
```

Para correr los 6 casos obligatorios de la sección 16 y ver el resultado esperado contra el obtenido:

```bash
python -m scripts.section16_cases
```

Ese comando escribe la evidencia en `docs_entrega/`, que no se sube a Git porque los manuales y el reporte
se entregan por correo.

## Cómo está organizado

```
main.py, iniciar.bat   abren el programa
src/structures/        nuestro AVL, BST, cola y pila
src/models/            los datos: eventos, reportes, zonas y el estado del escenario
src/services/          la lógica: procesar reportes, prioridad, asociaciones, deshacer, consultas
src/persistence/       guardar y cargar escenarios en JSON
src/gui/               la ventana en Tkinter (no toca los árboles, solo llama a los servicios)
data/                  archivos JSON de prueba
scripts/               casos de la sección 16 y generador de datos de ejemplo
tests/                 pruebas con unittest
```

## Archivos de prueba

Se cargan desde la pestaña **Archivos** (escenarios) o desde **Cola y estrés** (ráfagas).

| Archivo                                                                      | Cómo se carga   | Qué tiene                                                                                          |
| ---------------------------------------------------------------------------- | --------------- | -------------------------------------------------------------------------------------------------- |
| `data/scenarios/escenario_normal.json`                                       | Por topología   | Unos 30 eventos: activos, revisados, archivados, eliminados y una cola                             |
| `data/scenarios/escenario_estres.json`                                       | Por topología   | Árbol ordenado pero desbalanceado (modo estrés)                                                    |
| `data/scenarios/insercion_5.json`, `insercion_30.json`, `insercion_200.json` | Por inserciones | Listas de eventos `{"events": [...]}`                                                              |
| `data/scenarios/insercion_ascendente.json`                                   | Por inserciones | Claves en orden ascendente: ahí el BST se vuelve casi una lista                                    |
| `data/scenarios/invalido_topologia.json`                                     | Por topología   | Archivo con errores de orden y altura: se rechaza                                                  |
| `data/scenarios/invalido_insercion.json`                                     | Por inserciones | ID repetido y magnitud fuera de rango: se rechaza                                                  |
| `data/reports/rafaga_escenario_normal.json`                                  | Ráfaga          | Una de cada decisión: alta, confirmación, conflicto, corrección, antiguo, rechazado y reactivación |
| `data/reports/rafaga_200_estres.json`                                        | Ráfaga          | 200 altas para probar el modo estrés                                                               |
| `data/reports/rafaga_altas.json`                                             | Ráfaga          | 10 altas desde las cinco estaciones                                                                |
