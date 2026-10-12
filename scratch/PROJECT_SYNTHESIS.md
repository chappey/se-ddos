# DroneDash CLE (CLE_DDOS) - High-Level Project Synthesis

This document provides a high-level synthesis of the **Drone Delivery Operations System (CLE_DDOS)** requirements, domain model, and Sprint 1 deliverables based on [SE Project#1_DDOS_Fa26.md](SE%20Project%231_DDOS_Fa26.md).

---

## 1. System Mission & Core Domain: `CLE_DDOS`

The project requires designing and building the **Drone Delivery Operations System (CLE_DDOS)** for the **DroneDash Cleveland Delivery Company**, which provides same-day autonomous drone delivery of small packages across the Cleveland metropolitan area.

### Key Domain Concepts & Business Rules:
- **Customers & Orders:**
  - Serves individual and business customers throughout Greater Cleveland.
  - Customers have identifying/contact details and one or more registered addresses.
  - Delivery orders contain exactly one package and specify pickup/destination locations, requested delivery time, priority, and status.
  - Orders progress through strictly defined lifecycle stages (*Requested*, *Accepted*, *Scheduled*, *Assigned*, *In Transit*, *Delivered*, *Cancelled*, *Failed*) with rules preventing invalid state transitions.
- **Packages & Constraints:**
  - Track package ID, weight, dimensions, package type, and special handling instructions.
  - Must comply with strict company weight/size limitations and cannot exceed assigned drone payload capacities.
- **Drones & Fleet Management:**
  - Drones maintain unique ID, model, maximum payload, maximum flight range, current location, battery level, and operational status (*Available*, *Assigned*, *In Flight*, *Charging*, *Maintenance*, *Out of Service*).
  - Drones cannot have overlapping delivery assignments and must possess sufficient payload capacity, flight range, and battery reserve before dispatch.
- **Stations & Delivery Zones:**
  - Multiple drone base stations across Cleveland for departure, return, battery charging, and servicing.
  - Service territory is divided into delivery zones with active/inactive or permanent/temporary flight restrictions. Deliveries cannot be routed to destinations in actively restricted zones.
- **Scheduling & Drone Assignment:**
  - Multi-variable validation: checks package dimensions/weight, drone availability, battery levels, range, delivery priority, and flight zone restrictions before scheduling and assigning a drone.
- **Flight Execution & Exception Handling:**
  - Flight lifecycle logging: departures, in-transit telemetry, and delivery completions.
  - Comprehensive exception protocols for operational disruptions (battery depletion, severe weather, restricted airspace, hardware faults, recipient unavailability).
  - Exception resolution rules: rescheduling, reassignment to qualified backup drones, base station return, or cancellation.
- **Maintenance & Historical Auditing:**
  - Complete lifecycle tracking for drone maintenance and routine servicing.
  - Long-term operational audit records for past deliveries, customer order histories, failure analytics, and administrative reporting.

---

## 2. Sprint 1 Objectives (Release #1)

Sprint 1 is strictly a **requirements analysis and initial design sprint**—**no code implementation is permitted during this sprint**.

### Key Deliverables & Focus Areas:
1. **Software Requirements Specification (SRS):**
   - Completed using the *Simplified IEEE SRS Template* ([source_docs/Simplified_IEEE_SRS_Template_Agile_Projects.docx](source_docs/Simplified_IEEE_SRS_Template_Agile_Projects.docx)).
   - Remove all template italic instructions.
   - Specific, numbered, and testable **Functional Requirements** (e.g., account management, scheduling, assignment, status tracking, exceptions).
   - Relevant **Non-Functional Requirements** (Security, Performance, Usability, Reliability, Availability, Maintainability, Privacy).
2. **Actor & Use-Case Model:**
   - Define all human actors (Customers, Dispatchers/Admins, Maintenance Staff) and external systems.
   - Comprehensive UML Use-Case Diagram capturing relationships, `<<include>>`, and `<<extend>>` dependencies.
3. **Initial UML Class Diagram:**
   - Model foundational domain entities (`Customer`, `DeliveryOrder`, `Package`, `Drone`, `DroneStation`, `DeliveryZone`, `Restriction`, `DeliveryRecord`, `DeliveryException`, `MaintenanceRecord`).
   - Specify attributes, key operations/methods, multiplicities, and relationships.
4. **Activity Diagrams:**
   - UML Activity Diagrams for at least **two significant workflows** (e.g., *Order Scheduling & Drone Assignment*, *Exception Handling & Reassignment*).
   - Must depict decisions, conditions, concurrency/parallel activities, and clear start/end states.
5. **Additional Design Artifacts:**
   - Justified supplemental design models (e.g., State Machine Diagrams for Order/Drone lifecycles, Sequence Diagrams, Architecture diagrams).
6. **Design Decisions & Assumptions:**
   - Documented rationale behind operational assumptions, status transitions, and architectural choices.
7. **Team Review:**
   - Joint verification of requirements consistency and mutual alignment before final hand-off.

---

## 3. Key Milestones & Logistics

- **Sprint 1 Deadline:** October 13, 2026, at 11:59 PM.
- **Submission:** Single unified team deliverable.
- **Grading Rubric (100 Points Total):**
  1. *SRS Completeness & Organization:* 20 pts
  2. *Functional Requirements:* 20 pts
  3. *Non-Functional Requirements & Constraints:* 10 pts
  4. *Actors and Use Cases:* 15 pts
  5. *Initial Class Diagram:* 15 pts
  6. *Activity Diagrams:* 10 pts
  7. *Design Consistency & Decisions:* 5 pts
  8. *Team Review & Professional Presentation:* 5 pts
