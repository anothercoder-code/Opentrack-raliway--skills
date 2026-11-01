# Original Engine point and scale commands

`rolling_stock_operations[].kind=edit_engine_diagrams` accepts ordered
`add_point`, `update_point`, `move_point`, `delete_points`, `set_scale` and
`auto_scale` edits. `index` selects the diagram. A point reference is an exact
`curve=traction|braking` plus `point_index` in the array produced by previous
commands. These are persisted model operations, with no native window/event loop.

| Reviewed original function | Entry | Data behavior |
|---|---|---|
| `OTVisibleEngineZVView.mouseUp:` | `0x6e13d4` | New point classified by force sign; duplicate speed in that array is declined; sort destination by X |
| `OTDDiagram.existsPointForV:withZ:` | `0x47199c` | Speed uniqueness is per sign-selected array; zero selects traction |
| `OTEngineController.engineTakePointValues:` | `0x4d1714` | Set current point X/Y/interpolation directly, preserving array and order |
| `OTPointView.mouseDown:` | `0x56fe6c` | Drag model update keeps curve/type/order; force is clamped to the selected curve's sign |
| `OTDDiagram.deleteSelectedPoints` | `0x471b08` | Delete every occurrence of selected native point objects, in both arrays, retaining order |
| `OTDDiagram.setScalMaxSpeed:` / `setScalMaxPower:` | `0x4715dc` / `0x4715fc` | Clamp maxima to at least 10 |
| `OTDDiagram.setScalMinPower:` | `0x47161c` | Clamp positive minimum force to zero |
| `OTEngineDocument.autoScalePressed` | `0x4d6438` | Read stored Engine extrema; do nothing when speed or positive force is zero |
| `OTEngineZVView.setAutoScalFacs` | `0x4d8774` | Scale from global Engine extrema, including electrical braking |

The original manual section 5.2.6 also requires new points to be within diagram
scales. Add/move commands outside bounds return `applied=false` and the current
bounds. Zero-force additions go to traction; moving a braking point to positive
force clamps it to zero while retaining braking membership. Duplicate additions
keep the existing point by default; `if_speed_exists=error` gives an atomic error.

`update_point` represents the selected-value setter. It permits signed-int32
speed/force values, duplicate speeds, wrong-sign forces and points outside the
display scale. It does not sort or move the point between arrays. `move_point`
represents the physical data part of a valid drag: bounds and force-sign clamping
apply, interpolation stays unchanged, and point order stays unchanged. Pixel
conversion, intermediate mouse events and transient native selection state are
outside these data commands. New point types are `linear=1` or `hyperbolic=2`,
describing the segment on the left of that point. The native PointView's separate
curve-kind tags 0/1 must not be stored as these interpolation types.

`delete_points` takes `points` or `all_points=true`. Resolve all selected indices
before removing anything. Shared native point references within the diagram are
deleted together, as the original selected-object flags require. Empty arrays are
valid editable data. Adding points sorts their destination; equal-speed ties in
preexisting invalid data retain their input order in this API.

`set_scale` takes any supplied axis fields and applies the native clamps.
`auto_scale` defaults to `limits_source=saved_engine`, matching the native button's
stored Engine extrema and zero guard. `limits_source=curves` explicitly first
recomputes the Engine extrema from all its diagrams. The axis formula is
`floor((double(limit) * 1.1) / 10.0) * 10`, followed by native scale clamps. Do not
replace it with a ceiling or exact decimal arithmetic. In the audited x86 build,
entry `0x7214c0` calls `_controlfp(0x10000,0x30000)`, selecting 53-bit precision;
the meaning of those masks is documented by [Microsoft CRT](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/control87-controlfp-control87-2?view=msvc-170).
The double boundary `limit=-100` therefore yields `-120` before the minimum clamp.
Computed axes outside signed-int32 fail with `ENGINE_SCALE_OVERFLOW`; no native
invalid floating-point status or indefinite integer is synthesized.

The parent `recompute_engine_limits` defaults to true and refreshes speed/force
extrema at the end of the group, preserving stored kW power. Set it to false to
retain scalar limits except for explicit `limits_source=curves`. An auto-scale
command snapshots the prefix state; later point commands do not rescale it.

`opentrack_get_engine_diagram` reads one exact Engine/diagram. It returns at most
200 point rows, their native curve/index, scales, color and state diagnostics.
`curve=both` pages traction followed by braking. Unknown point types are reported
as `unknown`, not relabeled hyperbolic. Counts expose duplicate/nonmonotonic
speeds, negative speeds, wrong-sign forces and points outside scales. Record
validity and editable states do not establish runnable native traction behavior.

Review `point_command_results` and the complete `rolling_stock_changes_json`:
an ignored insertion is not a newly added point. Responses preview at most ten
command results. Existing 100,000 processed-row / 10,000 expanded-command limits
apply, plus 1,000,000 touched rows for point-command work. Native point layout is
OTDPoint v0 `iii`; mutations require the audited OTDDiagram v3 layout. Readers also
support v2. Earlier migrations, full native curve evaluation and other original
business functions remain separate requirements.
