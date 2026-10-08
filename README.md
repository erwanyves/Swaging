# Swaging — parametric swaging macro for FreeCAD

[![License: LGPL v2.1](https://img.shields.io/badge/License-LGPL_v2.1-blue.svg)](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html)
[![FreeCAD](https://img.shields.io/badge/FreeCAD-1.0%2B-orange.svg)](https://www.freecad.org)
[![Version](https://img.shields.io/badge/version-1.0-green.svg)](#version-history)

Creates a parametric swaging (a rolled-over lip) by revolution on a circular edge of a PartDesign body.

**Author:** Yves Guillou · **Version:** 1.0 · **License:** LGPL v2.1

> **Interface language:** the dialog is currently in **French only**. This README describes the labels in English.

---

## Features

- **Live preview.** The swaging is built immediately with the reference values. Each change in the dialog is visible at once in the 3D view, including the **flip direction** option.
- **Safe input.** An inconsistent value is never sent to the solver. The message appears under the fields, the confirm button is disabled, and the model keeps its last valid state.
- **One undo step.** **Keep** confirms, **Cancel** removes everything. A single Ctrl+Z undoes the whole swaging afterwards.
- **"Show the swaging alone, transparent"** displays the body before swaging plus the added material in transparency. The display helper is removed from the document when you confirm or cancel.
- **The body keeps its appearance:** material, colour and transparency.
- **Heavy parts.** Untick **Live preview** to suspend recomputes until confirmation.
- **Linked assemblies.** Works on a body linked into an assembly. A partially loaded linked document is completed first.
- **Editing afterwards.** Select a face or edge of an existing swaging and run the macro again to modify it.

---

## Requirements

- FreeCAD **1.0 or later** (developed and tested on 1.1), with the PartDesign and Sketcher workbenches
- No external dependency

---

## Installation

1. Download or clone this repository.
2. Copy `Swaging.FCMacro` and the `Swaging/` folder into your FreeCAD macro directory. To find it, open the menu **Macro → Macros…**: the directory is shown there.

```
Macro/
├── Swaging.FCMacro       ← entry point, the file you run
└── Swaging/
    ├── swg/              ← macro code
    └── data/swaging.json ← reference profile: 21 geometries, 52 constraints, 8 expressions
```

3. Run **Macro → Macros… → Swaging.FCMacro → Execute**, or add it to a toolbar.

---

## Usage

1. Select a **circular edge** (circle or arc) on a PartDesign body.
2. Run the macro. If nothing is selected, it asks for the click, and the 3D view stays usable.
3. Adjust the values. What you see is the real result, not an estimate.
4. **Keep** or **Cancel**.

## What the macro creates

| Object | Role |
|---|---|
| `SwagingVarSet` | the 7 editable parameters |
| `SwagingSketch` | the profile, attached to the edge, inside the body |
| `Swaging` | an additive 360° revolution in the same body |

Every dimension of the sketch is driven by an expression pointing at the VarSet. To change the swaging later, change a value in the VarSet.

| Parameter | Meaning |
|---|---|
| `InnerRadius` | inner radius, initialised to the edge radius |
| `SwagingRadius` | bend radius of the lip, inner side |
| `BaseThickness` | radial thickness at the base |
| `HeadThickness` | thickness at the tip (drives the chamfer = thickness / 3) |
| `AxialOffset` | height of the straight part before the bend |
| `LipLength` | total developed length: arc plus straight part |
| `SwagingAngle` | angle of the bent part |

`LipLength` must be at least the length of the bent part (SwagingRadius × SwagingAngle in radians). The macro checks this before creating anything.

## Positioning

The sketch is attached to the edge in `Concentric` mode, rotated 90° about X:

- sketch X → radial direction
- sketch Y → insertion axis, which is also the revolution axis
- origin → centre of the edge

**Flip direction** uses −90° instead: the lip starts on the other side of the edge plane.

The attachment is associative: if the supporting geometry moves, the swaging follows. Like any attachment by edge name, it remains sensitive to topological naming changes after an upstream recompute.

---

## Known limitations

- Interface in French only.
- The three created objects are not removed by the macro once confirmed. To remove a swaging afterwards, delete the revolution, the sketch and the VarSet.
- The reference profile in `data/swaging.json` was extracted from a reference model. Changing the profile means regenerating that file.

---

## Version history

**1.0** (October 2026): first public release.

---

## License

Licensed under the **GNU Lesser General Public License v2.1**. See [LICENSE](LICENSE).
