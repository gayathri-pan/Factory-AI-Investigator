# M-103 — Conveyor System: General Operating and Troubleshooting Reference

## 1. Purpose and asset identity
**Demo asset ID:** M-103  
**Represented equipment type:** Conveyor system  
**Plant:** Plant-A

This is a general reference for the Factory AI Investigator demonstration. It is not a manual for a verified conveyor make or model. The asset ID is a synthetic project label; confirm the actual conveyor type, drive arrangement, sensor placement, and site procedures before applying this information to real equipment.

## 2. Equipment overview
A conveyor transports materials using a belt, rollers, chain, or another conveying mechanism driven by motors and mechanical transmission components. A particular installation may include gearboxes, bearings, tensioning devices, tracking controls, guarding, emergency stops, and material-detection systems.

The project data includes `temperature`, `vibration`, `pressure`, `rpm`, and `power_consumption`. These names alone do not establish sensor location, units, or which subsystem is monitored.

## 3. Common fault categories and symptoms
These are hypotheses to evaluate with operating evidence:

- **Drive, motor, or gearbox concern:** an RPM or power change combined with temperature or vibration changes may warrant investigation of the drive train.
- **Bearing or roller concern:** recurring vibration or a local temperature trend may justify an inspection by qualified maintenance staff.
- **Belt/chain tracking, tension, or obstruction:** may affect load and drive behavior, but cannot be diagnosed from these five channels alone.
- **Changing material load:** can change power and speed behavior without indicating a fault; compare with throughput and operating state if available.
- **Pressure-system issue:** relevant only if the pressure channel is confirmed to monitor an installed pneumatic or hydraulic subsystem.
- **Sensor/telemetry issue:** spikes, drops, flat readings, and gaps may be measurement or communications problems.

## 4. Sensor investigation guide
### Temperature
Compare with the local baseline and identify whether the change is sustained or repeated. Correlate it with vibration, RPM, power, load, and maintenance history.

### Vibration
Check for isolated peaks versus recurring or sustained changes. If safe and supported by approved procedures, maintenance staff can inspect relevant rotating components. Do not diagnose a specific bearing or gearbox fault from the sensor alone.

### Pressure
Confirm which system is measured. Do not infer a belt, bearing, or hydraulic problem from a pressure signal unless the asset documentation connects that channel to the subsystem.

### RPM
Compare speed behavior with the expected operating state and load, if available. A speed drop could reflect load, control behavior, a drive issue, or sensor error.

### Power consumption
Look for sustained shifts and correlation with speed or load. A change may reflect material throughput, a jam, mechanical resistance, or a normal operating transition; more evidence is needed to distinguish them.

## 5. Safe investigation procedure
1. Record the conveyor ID, timestamp, sensor channel, and observed pattern.
2. Check operating state, load/throughput, alarms, and whether the conveyor was starting, stopping, or running steadily.
3. Compare sensor trends before, during, and after the event.
4. Correlate channels and review prior incidents or maintenance records.
5. If obstruction, tracking, tension, or rotating-component issues are suspected, follow the approved isolation and inspection procedure.
6. Record facts separately from possible causes and escalate unresolved concerns.

Never clear a jam or approach moving belts, chains, rollers, or drive components while energized. Never bypass emergency stops or guards. Use site lockout/tagout and approved conveyor safety procedures.

## 6. Preventive maintenance topics
Use the actual OEM/site schedule for belt or chain condition, alignment/tracking, tension, rollers, bearings, gearbox, lubrication, motor/drive, guarding, and emergency-stop checks. Do not invent intervals; record inspections and recurring faults.

## 7. Useful evidence
- Start/stop state and load/throughput, if available
- Sensor readings with aligned timestamps
- Drive/controller alarms
- Location of the sensor and monitored subsystem
- Inspection notes for belt/chain, rollers, bearings, and drive components
- Recent maintenance and repeated-event history

## 8. Limitations and references
This document provides general conveyor troubleshooting context, not verified OEM instructions. The synthetic sensor table does not establish a conveyor's design or operating limits. Consult the specific conveyor manufacturer documentation and approved site procedures for real maintenance and safety decisions.
