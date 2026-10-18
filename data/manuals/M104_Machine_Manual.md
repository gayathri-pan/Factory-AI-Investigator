# M-104 — Hydraulic Press: General Operating and Troubleshooting Reference

## 1. Purpose and asset identity
**Demo asset ID:** M-104  
**Represented equipment type:** Hydraulic press  
**Plant:** Plant-A

This is a general reference for the Factory AI Investigator demonstration, not an OEM manual for a verified press. M-104 is a synthetic project label. The actual press design, pressure sensor location, control logic, guarding, and approved safety procedure must be confirmed before applying this information to physical equipment.

## 2. Equipment overview
A hydraulic press uses a hydraulic power system and actuator to apply force during a press cycle. Depending on its design, it may include a pump, reservoir, valves, cylinders, filters, seals, pressure instrumentation, motor/drive, controls, and safeguarding.

The synthetic dataset includes `temperature`, `vibration`, `pressure`, `rpm`, and `power_consumption`. The dataset does not identify exact sensor placement, units, hydraulic circuit design, rated pressure, or OEM limits.

## 3. Common fault categories and symptoms
These are investigation hypotheses, not confirmed diagnoses:

- **Hydraulic-fluid heating:** a sustained temperature rise may justify checking the approved fluid, cooling, duty-cycle, and maintenance records.
- **Pressure instability or loss:** a pressure change may warrant checking the measured circuit, cycle phase, alarms, and service history. Do not infer leakage or valve failure from pressure alone.
- **Pump or motor/drive concern:** correlated changes in vibration, RPM, power, and pressure can help prioritize an inspection, but do not prove a specific component failure.
- **Mechanical or process-load change:** readings can vary across press phases and workpiece loads; compare like-for-like cycle stages.
- **Sensor/telemetry issue:** abrupt spikes, drops, flat readings, or missing samples may arise from instrumentation or data acquisition.

## 4. Sensor investigation guide
### Temperature
Compare the trend with the machine's recent baseline and the press-cycle phase. Correlate with pressure, RPM, and power. Do not define a maximum allowable temperature without verified specifications.

### Vibration
Check for repeated or sustained changes and align them with pump/drive operation if known. A vibration anomaly alone does not identify pump, bearing, or alignment failure.

### Pressure
Confirm the exact circuit and measurement point. Compare readings at equivalent cycle phases and review alarms and maintenance notes. Pressure changes must be interpreted against the actual press design and approved operating procedure.

### RPM
If the channel monitors a pump or motor, compare it with the expected operating state. Confirm that interpretation from the asset configuration rather than assuming the channel's physical source.

### Power consumption
Compare power behavior with cycle phase, pressure, and RPM. A change may reflect load or operating state as well as a possible equipment issue.

## 5. Safe investigation procedure
1. Record timestamp, sensor channel, press-cycle state, and observed values.
2. Compare readings at equivalent cycle phases where that information exists.
3. Review alarms, recent maintenance, fluid/service records, and previous events.
4. Confirm the pressure sensor's circuit and the identity of each monitored component.
5. Escalate abnormal behavior to qualified maintenance personnel using approved procedures.
6. Document the evidence, plausible alternatives, and missing information.

**Hydraulic presses can present severe crushing and stored-energy hazards.** Never reach into the point of operation, defeat safeguarding, loosen a pressurized connection, or rely on a control stop alone for maintenance. Use the manufacturer's isolation/depressurization procedure and site lockout/tagout requirements.

## 6. Preventive maintenance topics
Follow the actual press OEM schedule for hydraulic-fluid condition, filters, leaks, hoses/pipes, seals, pump, valves, cylinder, motor/drive, instrumentation, guarding, and safety systems. Never prescribe a pressure limit, fluid specification, or maintenance interval without the verified machine documentation.

## 7. Useful evidence
- Press cycle phase and operating state
- Pressure channel location and units
- Temperature, vibration, RPM, and power trends with aligned timestamps
- Controller alarms and operator observations
- Fluid/filter service history and previous maintenance reports
- Verified hydraulic diagram and OEM procedure

## 8. Limitations and references
This is general hydraulic-press context for a synthetic demo. It is not an approved service procedure and does not establish rated pressure or safe limits. Use the exact press manufacturer's manual, hydraulic diagram, and approved plant procedures for real equipment.
