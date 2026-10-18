# M-102 — Milling Machine: General Operating and Troubleshooting Reference

## 1. Purpose and asset identity
**Demo asset ID:** M-102  
**Represented equipment type:** Milling machine  
**Plant:** Plant-A

This document is a general reference for the Factory AI Investigator demonstration, not an OEM manual for a verified make or model. The asset ID is a synthetic project label. Confirm the actual machine design, sensor placement, and site procedures before using this guidance on real equipment.

## 2. Equipment overview
A milling machine removes material with a rotating cutting tool while the workpiece and/or tool move along controlled axes. Depending on its design, it may have a spindle, feed drives, workholding, lubrication, coolant delivery, guarding, and manual or CNC controls.

The synthetic dataset supplies `temperature`, `vibration`, `pressure`, `rpm`, and `power_consumption`. It does not identify exact sensor locations, measurement units, calibration, or manufacturer limits.

## 3. Common fault categories and symptoms
Treat these as possibilities to investigate, not automatic conclusions:

- **Tool wear, damage, or imbalance:** may be accompanied by changes in vibration, temperature, or power; confirm with tooling condition and process context.
- **Spindle or feed-drive concern:** recurring vibration, unusual speed behavior, or a persistent temperature trend may warrant a qualified inspection.
- **Coolant or lubrication concern:** temperature behavior may be relevant, but verify that the sensor and machine configuration support that interpretation.
- **Changing cut/load:** power and RPM may change because of material, tool engagement, feed, program, or operating mode.
- **Measurement or communication issue:** isolated spikes, drops, repeated identical values, missing timestamps, or implausible jumps may indicate sensor/telemetry problems.

## 4. Sensor investigation guide
### Temperature
Compare the reading with nearby values and the recent baseline. Check the timing of the machining cycle and look for supporting changes in vibration, RPM, or power.

### Vibration
Determine whether the event is a one-point peak, a repeated pattern, or a sustained shift. Compare it with RPM and process context. Vibration alone does not establish tool damage, imbalance, or bearing failure.

### Pressure
Identify the system being measured before interpreting the signal. If the channel is associated with coolant or pneumatics, consult the machine-specific diagram and approved procedure rather than assuming its function.

### RPM
Compare actual readings with the commanded or expected operating state when that information is available. Check for drops, oscillation, or a stuck value, and correlate with power and vibration.

### Power consumption
Check whether the change aligns with cutting engagement, speed changes, tool changes, or another operating transition. A power change alone does not establish an electrical fault.

## 5. Safe investigation procedure
1. Capture the asset ID, event time, sensor channel, trend, and machine operating state.
2. Compare before/during/after readings and check whether the pattern repeats.
3. Correlate channels using timestamps; distinguish simultaneous evidence from unrelated changes.
4. Review alarms, tooling records, recent setup changes, and maintenance history.
5. Refer suspected tooling, spindle, drive, coolant, or lubrication issues to qualified personnel.
6. Record the evidence and uncertainty; do not state a root cause without support.

Do not handle the tool, workpiece, chips, or spindle until the machine is in the approved safe state. Never bypass guards or interlocks. Follow site lockout/tagout procedures.

## 6. Preventive maintenance topics
Follow the actual OEM schedule for tool condition, spindle and axis lubrication, coolant, filters, workholding, guarding, drive components, and electrical systems. Maintenance intervals and tolerances must come from the machine's verified documentation.

## 7. Useful evidence
- Machine state, active program/operation, and commanded speed if available
- Sensor readings and timestamps around the event
- Controller alarms and operator observations
- Tool/workpiece details and recent setup changes
- Maintenance records and previous similar events
- Sensor placement, unit, and calibration status

## 8. Limitations and references
This is general milling-machine guidance for a synthetic demonstration. It does not define OEM specifications or numeric safe/unsafe thresholds. For real equipment, consult the exact manufacturer's manual, machine drawings, and approved plant procedures. General public safety guidance can supplement but not replace these sources.
