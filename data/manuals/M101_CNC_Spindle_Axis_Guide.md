# M-101 — CNC Spindle and Axis System Guide

## Scope and applicability
**Project asset:** M-101  
**Assumed equipment type:** CNC machine  
**Document type:** General troubleshooting reference prepared for the Factory AI Investigator demo.

This guide supplements `M101_Machine_Manual.md`. It is not an OEM service manual and is not based on a verified machine make or model. Confirm the actual configuration, sensor locations, units, alarm meanings, and approved site procedures before applying this guidance to physical equipment.

## System overview
A CNC machine commonly coordinates spindle rotation and controlled axis movement through a controller and drive systems. Depending on the model, associated systems may include spindle bearings, axis guides and drives, lubrication, coolant, toolholding, workholding, and an automatic tool changer. The exact equipment fitted to M-101 has not been established by the synthetic dataset.

The project telemetry names are `temperature`, `vibration`, `pressure`, `rpm`, and `power_consumption`. These names do not identify the monitored component, physical sensor location, or engineering units.

## Symptoms and possible investigation paths
- **Spindle vibration change:** compare the trend with spindle speed, machining state, tooling changes, and prior observations. Tool imbalance, tool condition, workholding, and rotating-component wear are hypotheses, not diagnoses.
- **Temperature rise:** determine which component is measured and whether the rise is sustained. Review operating conditions and approved coolant/lubrication indications.
- **Unexpected RPM behavior:** compare the reading with the commanded or expected state if available. Consider program changes, operating transitions, drive alarms, and measurement faults.
- **Power change:** correlate with spindle speed, cutting engagement, material, tool, and cycle phase before deciding that a fault is present.
- **Pressure change:** interpret only after confirming whether the channel monitors a hydraulic, pneumatic, or coolant subsystem.
- **Flat, missing, or implausible readings:** check timestamps, sensor configuration, communication status, and corroborating channels before treating the pattern as mechanical damage.

## Investigation checklist
1. Record asset ID, timestamp, affected channel, observed values, machine state, and any controller alarm.
2. Compare readings before, during, and after the event; look for persistence or recurrence.
3. Check whether multiple channels change at aligned timestamps.
4. Review recent tooling, workholding, program, setup, coolant, or maintenance changes where records are available.
5. Compare observations with relevant OEM documentation and approved maintenance history.
6. Separate measured evidence from hypotheses and record missing information.

## Maintenance topics to verify against the OEM schedule
Qualified personnel should follow verified procedures for spindle and axis lubrication, toolholder/tool condition, workholding, coolant, filters, drive diagnostics, guarding, and tool-change mechanisms where installed. Do not infer service intervals from this guide.

## Safety
Do not enter the work envelope, touch rotating tooling, remove guarding, or troubleshoot energized drives outside an approved procedure. Follow the manufacturer's safe-state, isolation, and site lockout/tagout requirements. Never bypass guards or interlocks.

## Evidence useful to the investigator
- Spindle speed or commanded speed, if available
- Program/cycle phase and recent setup or tooling change
- Controller alarm text and timestamp
- Channel location, unit, calibration, and data-quality status
- Related maintenance and previous event records

## Limitations
This document contains general troubleshooting context only. No OEM limits, sensor calibration values, or verified physical causes are established here. Use the actual machine documentation for operational decisions.
