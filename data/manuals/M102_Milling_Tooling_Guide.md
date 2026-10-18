# M-102 — Milling Tooling and Feed-System Guide

## Scope and applicability
**Project asset:** M-102  
**Assumed equipment type:** Milling machine  
**Document type:** General troubleshooting reference prepared for the Factory AI Investigator demo.

This guide supplements `M102_Machine_Manual.md`. It is not an OEM manual for a verified make or model. Confirm the actual machine configuration, measurement locations, units, and site procedures before using this guidance on physical equipment.

## System overview
A milling machine removes material using a rotating cutting tool and relative movement between tool and workpiece. Depending on design, relevant systems can include the spindle, toolholder, cutting tool, feed axes, workholding, coolant delivery, lubrication, and controller. The exact M-102 configuration is not established by the synthetic sensor table.

The project telemetry names are `temperature`, `vibration`, `pressure`, `rpm`, and `power_consumption`. Their exact physical sources and engineering units are not specified.

## Symptoms and possible investigation paths
- **Vibration during cutting:** compare like-for-like operations and consider tool condition, toolholder seating, workholding, cutting conditions, or rotating components as hypotheses. A single vibration peak cannot identify the cause.
- **Temperature change:** check component identity, duration, cycle phase, and recurrence. Review approved coolant and lubrication indicators where applicable.
- **Unexpected RPM:** align the reading with commanded speed, program phase, and controller alarms if records are available.
- **Power change:** compare with tool engagement, material, feed/speed settings, and workpiece conditions before attributing it to a fault.
- **Pressure anomaly:** identify the measured subsystem first; do not assume the channel represents coolant pressure.
- **Repeated identical values or data gaps:** consider sensor resolution, acquisition, timestamps, and communication status as well as equipment causes.

## Investigation checklist
1. Capture asset ID, event time, channel, readings, operating state, and alarm messages.
2. Compare the event with the same or similar cycle phase where possible.
3. Check time-aligned trends across all available channels.
4. Review recent tool/workpiece changes, setup records, controller messages, and maintenance history.
5. Verify proposed inspections against the machine's approved procedure.
6. Record supporting evidence, conflicting evidence, and uncertainty separately.

## Maintenance topics to verify against the OEM schedule
The verified machine-specific plan may address cutting-tool condition, toolholder and spindle checks, workholding, feed-axis lubrication, coolant condition and delivery, filters, guarding, and drive diagnostics. This guide does not define tolerances or maintenance intervals.

## Safety
Do not touch the cutter, clear chips by hand, adjust workholding, or enter the work envelope while the machine is in an unsafe state. Use approved chip-removal tools and procedures. Never bypass guarding or interlocks, and follow OEM safe-state and site lockout/tagout rules for maintenance.

## Evidence useful to the investigator
- Operation/program phase and commanded speed/feed, if available
- Tool type/condition and recent tool or workpiece changes
- Controller alarms and timestamped operator notes
- Sensor location, units, calibration, and data-quality information
- Related maintenance records and prior similar events

## Limitations
This is general milling-machine guidance, not a verified OEM procedure. It establishes no numeric safe/unsafe thresholds and cannot diagnose a specific tooling, spindle, or feed-system fault from sensor data alone.
