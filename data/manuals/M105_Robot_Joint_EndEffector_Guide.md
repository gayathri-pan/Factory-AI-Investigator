# M-105 — Robot Joint, Drive and End-Effector Guide

## Scope and applicability
**Project asset:** M-105  
**Assumed equipment type:** Industrial robotic arm  
**Document type:** General troubleshooting reference prepared for the Factory AI Investigator demo.

This guide supplements `M105_Machine_Manual.md`. It is not an OEM manual for a verified robot model or cell. Confirm the actual robot, controller, joint configuration, end effector, payload, sensor mapping, and risk-assessed site procedure before using the guidance on physical equipment.

## System overview
An industrial robot follows programmed motion using joint mechanisms, motors/drives, feedback devices, a controller, and a tool or end effector. A cell may also include cables, brakes, gearboxes, pneumatic or hydraulic tooling, workpieces, external axes, guarding, and safety-rated controls. The specific M-105 configuration has not been established by the synthetic dataset.

The available project telemetry names are `temperature`, `vibration`, `pressure`, `rpm`, and `power_consumption`. The source component, unit, and calibration for each channel are not specified.

## Symptoms and possible investigation paths
- **Temperature or vibration change:** identify the monitored component and correlate with robot motion, joint activity, payload, and controller alarms. Do not infer gearbox wear or collision damage from a generic sensor signal alone.
- **RPM or power change:** compare similar motion segments and operating modes. Acceleration, payload, trajectory, and tool operation may affect readings.
- **Pressure anomaly:** first confirm whether the channel belongs to a pneumatic/hydraulic end effector or another pressure system; otherwise its relevance is unknown.
- **Changes after a program/tool/payload update:** compare configuration and task history before interpreting the change as equipment degradation.
- **Flat or implausible values:** review data quality, communication status, timestamps, and controller diagnostics.

## Investigation checklist
1. Record robot/cell ID, event timestamp, operating mode, task/trajectory context if available, and controller alarms.
2. Compare telemetry across equivalent motion segments or payload conditions where possible.
3. Check whether a program, tool, payload, process, or cell configuration changed near the event.
4. Verify sensor mapping and correlate channels using aligned timestamps.
5. Review approved controller diagnostics and maintenance history through authorized interfaces.
6. Refer suspected joint, drive, end-effector, or safety-system faults to qualified robotics personnel. Separate observations from hypotheses.

## Maintenance topics to verify against the robot OEM schedule
The actual OEM plan may cover joint/gearbox service, brakes, cables/connectors, end-effector and tool mounting, lubrication where applicable, controller cooling, backup/configuration management, cell guarding, and safety devices. Requirements vary by model and installation; this guide gives no maintenance intervals or acceptance limits.

## Safety
Robots can move unexpectedly and create crushing, pinch, and impact hazards. Never enter the robot envelope or attempt hands-on maintenance while energized outside the approved safe-access procedure. Do not bypass safety-rated functions. Follow the exact robot/cell isolation, stored-energy control, and lockout/tagout process.

## Evidence useful to the investigator
- Controller alarms and diagnostic messages
- Task/program, motion segment, operating mode, and payload/tool state if available
- Sensor mapping, units, calibration, and data-quality status
- Timestamp-aligned trends and recent configuration changes
- Maintenance records and prior similar events

## Limitations
This is general industrial-robot context for a synthetic demo, not a manufacturer-approved service procedure. The data do not establish the robot model, joint mapping, payload rating, operating limits, or a confirmed physical cause.
