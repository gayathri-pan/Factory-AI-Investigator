# M-105 — Robotic Arm: General Operating and Troubleshooting Reference

## 1. Purpose and asset identity
**Demo asset ID:** M-105  
**Represented equipment type:** Industrial robotic arm  
**Plant:** Plant-A

This is a general reference for the Factory AI Investigator demonstration, not an OEM manual for a verified robot model. The asset ID is a synthetic project label. The actual robot, controller, end effector, payload, installation, sensor locations, and approved safety procedures must be verified before applying guidance to physical equipment.

## 2. Equipment overview
An industrial robotic arm moves a tool or payload through programmed joint and/or Cartesian trajectories. A cell may include joint motors and drives, gearboxes, brakes, encoders, an end effector, controller, cables, guarding, safety-rated controls, and external equipment.

The synthetic project provides `temperature`, `vibration`, `pressure`, `rpm`, and `power_consumption`. These generic channel names do not prove that a channel is measured at a particular joint, motor, pneumatic gripper, or controller.

## 3. Common fault categories and symptoms
Use these as possible investigation paths, not automatic diagnoses:

- **Joint drive or gearbox concern:** a recurring vibration or temperature change may justify review of joint-specific alarms and maintenance records.
- **Motion or load change:** RPM and power may change with trajectory, acceleration, payload, or operating mode. Compare like-for-like motions where possible.
- **End-effector or pneumatic-system concern:** pressure is relevant only if the channel is verified to monitor an installed pneumatic/hydraulic gripper or other pressure system.
- **Cable, sensor, or telemetry concern:** flat signals, spikes, drops, or data gaps may indicate measurement or communications issues; inspect logs and configuration.
- **Program or process change:** a new trajectory, payload, tool, or cycle can change readings without indicating equipment damage.

## 4. Sensor investigation guide
### Temperature
Determine which component the channel measures before interpreting a trend. Compare with recent operation and correlated drive/motion evidence; do not assign a joint-level root cause without location data.

### Vibration
Look for repeated patterns and align them with robot motion, joint activity, and load if available. Vibration alone cannot confirm gearbox wear, collision damage, or bearing failure.

### Pressure
Verify whether the signal belongs to an end effector or another pressure-operated subsystem. Compare against gripper/cell state and approved documentation; otherwise report the channel's meaning as unknown.

### RPM
Establish which motor or motion component is monitored. Compare with the commanded movement and operating mode if available. Do not assume a single RPM value represents the whole robot.

### Power consumption
Compare readings across similar cycles and payloads. Correlate with motion state, RPM, and alarms. A power shift alone does not prove a motor or controller failure.

## 5. Safe investigation procedure
1. Record robot/cell ID, event time, operating mode, sensor channel, and available controller alarms.
2. Compare readings across equivalent motion/cycle states where possible.
3. Check whether the event coincides with a program, payload, tool, or end-effector change.
4. Review robot-controller diagnostics and maintenance history through approved interfaces.
5. Refer suspected joint, drive, end-effector, or safety-system issues to qualified robot personnel.
6. Document observations, hypotheses, and missing evidence separately.

**Robots can move unexpectedly and create crushing, impact, and pinch hazards.** Do not enter the robot envelope or attempt hands-on checks while energized. Never bypass safety-rated functions. Follow the robot manufacturer's cell-specific isolation, safe-access, and lockout/tagout procedures.

## 6. Preventive maintenance topics
Follow the verified robot OEM schedule for joint/gearbox inspection, lubrication where applicable, brakes, cables, connectors, end effector, mounting, controller cooling, backups, and safety systems. Maintenance requirements differ by model and installation; do not invent intervals or limits.

## 7. Useful evidence
- Robot program/task and operating mode
- Motion segment, payload, and end-effector state if available
- Controller alarms and joint-specific diagnostic messages
- Sensor channel location, units, and timestamp alignment
- Recent tool, payload, program, or cell changes
- Previous service reports and verified robot documentation

## 8. Limitations and references
This is general industrial-robot context for a synthetic demo, not an OEM procedure. The available sensor table does not establish robot make/model, joint mapping, payload rating, or operating limits. Use the exact robot manufacturer's manual, cell risk assessment, and approved site safety procedures for real equipment.
