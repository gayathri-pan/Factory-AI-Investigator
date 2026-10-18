# M-103 — Conveyor Drive, Belt and Tracking Guide

## Scope and applicability
**Project asset:** M-103  
**Assumed equipment type:** Conveyor system  
**Document type:** General troubleshooting reference prepared for the Factory AI Investigator demo.

This guide supplements `M103_Machine_Manual.md`. It is not an OEM manual for a verified conveyor make or model. Confirm the actual conveyor type and the applicable sensor locations and site procedures before applying this information to physical equipment.

## System overview
A conveyor moves material using a conveying mechanism and drive system. Depending on the installation, relevant components may include a motor, gearbox, drive pulley or sprocket, belt or chain, rollers, bearings, tensioning and tracking arrangements, guards, and emergency-stop devices. The synthetic project does not verify which components are fitted to M-103.

The project telemetry names are `temperature`, `vibration`, `pressure`, `rpm`, and `power_consumption`. The physical source and units of each channel remain unverified.

## Symptoms and possible investigation paths
- **Power changes:** correlate with material load, throughput, starts/stops, and operating state. A change can result from normal load variation as well as a possible issue.
- **RPM or speed change:** compare with the expected operating condition and controller/drive alarms. Do not conclude that belt slip or a drive fault occurred without corroboration.
- **Vibration or temperature trend:** check which component is monitored and whether the change persists or recurs. Drive, bearing, roller, or gearbox issues are hypotheses requiring additional evidence.
- **Possible tracking, tension, or obstruction issue:** use operator reports, approved visual inspections, and installed monitoring information. The five generic channels alone cannot confirm belt misalignment or obstruction.
- **Pressure change:** relevant only if a documented pressure-operated subsystem is installed and measured by that channel.
- **Flat signals, spikes, or missing samples:** verify sensor/data quality and timestamps before treating them as mechanical symptoms.

## Investigation checklist
1. Record event time, conveyor state, affected channel, and observations from operator or control-system records.
2. Determine whether the event occurred during startup, shutdown, steady running, or a load transition.
3. Compare trends before, during, and after the event and align sensor timestamps.
4. Review drive alarms, material flow/load information, and prior maintenance reports if available.
5. Route suspected mechanical issues to qualified personnel under the approved isolation procedure.
6. Record what is observed separately from what is only suspected.

## Maintenance topics to verify against the equipment schedule
The actual manufacturer/site plan may cover belt or chain condition, tracking and tension where applicable, pulleys/sprockets, rollers, bearings, gearbox, lubrication, motor/drive, guards, and emergency stops. Do not invent inspection intervals or allowable wear limits.

## Safety
Never reach near moving belts, chains, rollers, pulleys, or drive components. Do not clear jams, adjust tracking/tension, or remove guards while the equipment is operating. Use approved isolation and lockout/tagout procedures, and never bypass emergency stops or guards.

## Evidence useful to the investigator
- Start/stop and operating-state records
- Load/throughput information, if available
- Timestamp-aligned sensor trends and controller/drive alarms
- Confirmed sensor location and engineering units
- Inspection findings and recent repair/maintenance history

## Limitations
This guide provides general conveyor troubleshooting context only. The dataset does not establish the conveyor design, sensor mapping, OEM limits, or root cause. Refer to verified equipment documentation and site procedures for physical maintenance and safety actions.
