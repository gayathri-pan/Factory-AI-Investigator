# M-101 — CNC Machine: General Operating and Troubleshooting Reference

## 1. Purpose and asset identity
**Demo asset ID:** M-101  
**Represented equipment type:** Computer Numerical Control (CNC) machine  
**Plant:** Plant-A

This is a general reference for the Factory AI Investigator demonstration. The asset ID and plant assignment are project labels; this is not an OEM manual for a verified make or model. Confirm the actual machine configuration and approved site procedures before applying guidance to physical equipment.

## 2. What a CNC machine does
A CNC machine uses a programmed controller to coordinate axes, spindle motion, tooling, and machining operations. Depending on the machine configuration, it may include a spindle drive, axis drives, lubrication, coolant delivery, workholding, guarding, and tool-change mechanisms.

The sensor channels available in this synthetic project are `temperature`, `vibration`, `pressure`, `rpm`, and `power_consumption`. They are generic telemetry channels; the dataset does not establish the physical sensor location, unit, calibration, or OEM operating range.

## 3. Common fault categories and symptoms
These are investigation hypotheses, not diagnoses:

- **Spindle or bearing-related concern:** a sustained or recurring vibration change, temperature rise, or unusual power pattern may justify inspection by qualified maintenance staff.
- **Cooling or lubrication concern:** a temperature trend or change during machining may warrant checking the approved coolant/lubrication indicators and service history.
- **Drive, load, or cutting-process change:** RPM and power changing together may reflect a change in operating load, program, tooling, or drive behavior; check the operating context before attributing a cause.
- **Pressure-system concern:** a pressure change matters only if the channel is confirmed to monitor a relevant pneumatic, hydraulic, or coolant circuit.
- **Sensor or telemetry issue:** isolated spikes, drops, flat lines, timestamp gaps, or implausible transitions may reflect measurement or communication problems rather than machine damage.

## 4. Sensor investigation guide
### Temperature
Compare the event with nearby readings and the machine's own recent baseline. Check whether the change is brief, gradual, sustained, or repeated. Look for simultaneous changes in vibration, RPM, and power.

### Vibration
Compare peaks with the surrounding trend and with RPM/load context. Repeated or sustained changes deserve more attention than a single uncorroborated point. Do not infer a specific bearing or alignment fault from vibration alone.

### Pressure
First establish what system the pressure channel represents. Compare the signal with related operating states and maintenance notes; do not assume it is coolant or hydraulic pressure without asset documentation.

### RPM
Look for unexpected changes, oscillation, or a flat signal. Interpret RPM alongside the operating cycle, commanded speed if available, vibration, and power.

### Power consumption
Compare changes with RPM and process/load context. A rise or drop can have several causes and is not proof of electrical failure.

## 5. Safe troubleshooting workflow
1. Record asset ID, timestamp, channel, observed values, and the operating state if available.
2. Compare readings before, during, and after the event.
3. Check whether multiple channels change together and whether the pattern repeats.
4. Review the machine's approved operating instructions, alarms, and service history.
5. Ask qualified personnel to inspect the relevant subsystem when evidence warrants it.
6. Preserve the event log and record both supporting and conflicting evidence.

Never reach into the work envelope, remove guarding, bypass interlocks, or inspect rotating tooling while energized. Follow site lockout/tagout and approved maintenance procedures.

## 6. Preventive maintenance topics
Use the machine's actual OEM schedule for spindle and axis lubrication, coolant condition, filters, tooling, workholding, guarding, electrical enclosures, and drive-system checks. Record completed work and recurring symptoms. This reference does not define service intervals or acceptance limits.

## 7. Evidence to collect during an investigation
- Program/operation and machine state, if available
- Sensor trend and timestamps
- Alarm or controller messages
- Tooling/workpiece change or recent setup change
- Relevant service history and previous similar events
- Confirmed sensor location, unit, and calibration information

## 8. Limitations and references
This manual provides general CNC troubleshooting context, not verified OEM instructions. Do not invent temperature, vibration, pressure, RPM, or power thresholds. For real equipment, use the exact manufacturer's operating and maintenance manual and approved plant procedures. Public safety guidance and standards can supplement—but not replace—those documents.
