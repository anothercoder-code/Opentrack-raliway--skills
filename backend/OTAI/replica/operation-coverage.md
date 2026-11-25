# Current saved-data operation coverage

176 original definitions retained. PE = partial source/bounded evidence; NR = not reassessed, not unsupported; NA = native replacement not required. A suffix `(n)` counts explicit bounded evidence cases, not completed original features. Export is assessed separately. See requirements.json for exact scopes/tests.

| ID | Requirement | Read | Generate | Modify | Export | Unavailable legacy entrypoints |
|---|---|---|---|---|---|---|
| M2.1 | Input Data | NR | PE (1) | NR | NR |  |
| M2.1.1 | Rolling Stock: Locomotives and Wagons | PE | PE (1) | PE | NR | opentrack_list_catalog |
| M2.1.2 | Track Layout Data | PE | PE (2) | PE | NR |  |
| M2.1.3 | Timetable Data | PE | PE (2) | PE | NR |  |
| M2.1.4 | Train Operations | NR | PE (2) | NR | NR |  |
| M2.2 | Simulation | NR | NA | NA | NA |  |
| M2.3 | Evaluations | PE | NR | NR | NR |  |
| M2.4 | Data Management in Open Track | PE | NR | PE | NR |  |
| M3.1 | Starting OpenTrack and File Management | PE | NR | PE | NR |  |
| M3.2 | OpenTrack Worksheet | NR | NR | NR | NR |  |
| M3.3 | Vertex | PE | PE (2) | PE | NR |  |
| M3.3.1 | Double Vertex Graphs (DVG) | PE | PE (2) | PE | NR |  |
| M3.3.2 | Station Reference Point  (Station Vertex) | PE | PE (1) | PE | NR |  |
| M3.4 | Edges (Sections of Railroad Track) | PE | PE (2) | PE | NR |  |
| M3.4.1 | Safety Elements | PE | NR | PE | NR |  |
| M3.5 | Connector Vertices | PE | PE (1) | PE | NR |  |
| M3.6 | Signals | PE (1) | PE (1) | PE (1) | NR |  |
| M3.7 | Stations | PE | PE (3) | PE | NR |  |
| M3.7.1 | Station Inspector | PE | PE | PE | NR |  |
| M3.7.2 | De ﬁning a Station Area | NR | PE (1) | NR | NR |  |
| M3.7.3 | Representing Stations with OpenTrack | NR | PE (1) | NR | NR |  |
| M3.7.4 | Station Database  (Stations) | PE | PE (1) | PE | NR |  |
| M3.8 | Power Supply Area | NR | NR | NR | NR |  |
| M3.9 | Additional Worksheet Objects | NR | NR | NR | NR |  |
| M3.9.1 | Instrument Windows | NR | NR | NR | NR |  |
| M3.9.2 | Plot Objects (Plot) | NR | NR | NR | NR |  |
| M3.9.3 | Graphical Elements | NR | NR | NR | NR |  |
| M3.9.4 | Text | NR | NR | NR | NR |  |
| M3.9.5 | Images (Photos-Drawings) | NR | NR | NR | NR |  |
| M3.10 | Behaviour of Objects on the Worksheet | NR | NR | NR | NR |  |
| M4.1 | Routes | PE | PE (1) | PE | NR |  |
| M4.1.1 | Automated Search for All Possible Routes from a Main Signal | PE | PE | PE | NR |  |
| M4.1.2 | Route Inspector | PE | PE | PE | NR |  |
| M4.1.3 | Preventing Deadlock on Routes | NR | NR | NR | NR |  |
| M4.1.4 | Signal Indication at the Main Signal | PE | NR | PE | NR |  |
| M4.1.5 | Slow Speed Zone | PE | NR | PE | NR |  |
| M4.1.6 | Approach Zone | PE | NR | PE | NR |  |
| M4.2 | Shuntings | PE | PE | PE (1) | NR |  |
| M4.2.1 | Overlaps (extended functionality) | PE | PE | PE | NR |  |
| M4.2.2 | De ﬁnition of Shunting Movements and Overlaps | PE | PE | PE (1) | NR |  |
| M4.3 | Paths | PE | PE (1) | PE | NR |  |
| M4.3.1 | Path Inspector | PE | PE | PE | NR |  |
| M4.3.2 | De ﬁning Paths in OpenTrack | PE | PE | PE | NR |  |
| M4.4 | Itineraries | PE | PE (1) | PE | NR |  |
| M4.4.1 | Itinerary Window | PE | PE | PE | NR |  |
| M4.4.2 | Creating a New Itinerary | PE | PE (1) | PE | NR |  |
| M4.4.3 | Editing an Itinerary | PE | PE | PE | NR |  |
| M5.1 | Trains Window | PE | PE (1) | PE (1) | PE | opentrack_list_catalog |
| M5.1.1 | Creating a New Train | PE | PE (1) | PE | NR | opentrack_list_catalog |
| M5.1.2 | Train Edit Panel | PE | PE | PE (1) | NR | opentrack_list_catalog |
| M5.2 | Locomotive Management (Engines) | PE | PE (1) | PE | PE | opentrack_get_engine_diagram, opentrack_list_catalog |
| M5.2.1 | Engines Window | PE | PE | PE | NR | opentrack_list_catalog |
| M5.2.2 | Tractive Effort/Speed Diagram (Z/V-Diagram) | PE | PE | PE | NR | opentrack_get_engine_diagram |
| M5.2.3 | Power System | PE | PE | PE | NR |  |
| M5.2.4 | Adhesion Behaviour | PE | PE | PE | NR |  |
| M5.2.5 | Locomotive Power Loss Function | PE | PE | PE | NR |  |
| M5.2.6 | Tractive Effort/Speed (Z/V Diagram) Window | PE | PE | PE | NR | opentrack_get_engine_diagram |
| M5.3 | Train Resistance Calculation | PE | NR | PE | NR |  |
| M5.3.1 | A - Traction Resistance | PE | NR | PE | NR |  |
| M5.3.2 | B - Acceleration Resistance | PE | NR | PE | NR |  |
| M5.4 | Examples | PE | NR | PE | NR |  |
| M5.4.1 | Braking Curve De ﬁnition Based on Braking Percent | PE | NR | PE | NR |  |
| M5.4.2 | Braking Calculations for Trains Operating Under ETCS Level 2 | PE | NR | PE | NR |  |
| M5.5 | Train Categories | PE | PE (1) | PE | NR | opentrack_list_catalog |
| M5.5.1 | Train Categories Window Description | PE | NR | PE | NR | opentrack_list_catalog |
| M5.5.2 | Dispatching Priority by Train Category | PE | NR | PE | NR |  |
| M5.5.3 | Initial Delay by Train Category | PE | NR | PE | NR |  |
| M5.5.4 | Station Delays by Train Category | PE | NR | PE | NR |  |
| M5.5.5 | Performance Distribution | PE | NR | PE | NR |  |
| M5.5.6 | Delay De ﬁnitions | PE | NR | PE | NR |  |
| M5.6 | Distribution Functions in OpenTrack | PE | NR | PE | NR |  |
| M6.1 | Course Management (Courses) | PE | PE (2) | PE (1) | PE |  |
| M6.1.1 | Courses/Services Window | PE | PE | PE (1) | NR |  |
| M6.1.2 | De ﬁning a New Course | PE | PE (1) | PE | NR |  |
| M6.2 | Timetable Database | PE | PE (2) | PE | PE |  |
| M6.2.1 | Time Format in OpenTrack | PE | PE (1) | PE | NR |  |
| M6.2.2 | Timetable Management Window | PE | PE | PE | NR |  |
| M6.2.3 | Recording a New Timetable Entry | PE | PE (2) | PE | NR |  |
| M6.3 | Connections | PE | PE | PE | NR |  |
| M6.3.1 | Recording a New Connection | PE | PE | PE | NR |  |
| M6.3.2 | Connection Examples | PE | PE | PE | NR |  |
| M6.3.3 | Split of Trains | PE | PE | PE | NR |  |
| M6.3.4 | Joining of Trains | PE | PE | PE | NR |  |
| M6.3.5 | Occupied Entry | PE | PE | PE | NR |  |
| M6.3.6 | Turnround | PE | PE | PE | NR |  |
| M6.3.7 | Example: Train Split and Continue Maneuver | PE | PE | PE | NR |  |
| M7.1 | Calculation Basis of the Simulation | NR | NA | NA | NA |  |
| M7.1.1 | Modeling Braking Behaviour | NR | NA | NA | NA |  |
| M7.1.2 | Stopping at Stations and Stops | NR | PE (1) | NA | NA |  |
| M7.2 | Behaviour of Protection Systems | PE (1) | NA | PE (1) | NA |  |
| M7.2.1 | Moving Block Signal System | NR | NA | NA | NA |  |
| M7.3 | Dispatching in OpenTrack | NR | NA | NA | NA |  |
| M8.1 | Preferences | PE | NR | PE | NR |  |
| M8.2 | Running and Monitoring an OpenTrack Simulation | PE | NR | NR | NR |  |
| M8.2.1 | Simulation Window | PE | NR | NR | NR |  |
| M8.2.2 | Output Window | PE | NR | NR | NR |  |
| M8.3 | Incidents | PE | PE | PE | NR |  |
| M8.3.1 | Incidents Window | PE | PE | PE | NR |  |
| M8.3.2 | Creating Incident Sets | PE | PE | PE | NR |  |
| M8.3.3 | Schedule Incidents | PE | PE | PE | NR |  |
| M8.4 | Train Graph (Train Diagram) | PE | NR | PE | NR |  |
| M8.4.1 | Corridor Level Simulation | PE | NR | PE | NR |  |
| M8.5 | Working with Timetable Data on the Train Graph | PE | NR | PE | NR |  |
| M8.6 | Monitoring the Simulation | NR | NR | NR | NR |  |
| M8.6.1 | Animation | NR | NR | NR | NR |  |
| M8.6.2 | Messages During the Simulation | NR | NR | NR | NR |  |
| M8.7 | Evaluations | PE | NR | NR | NR |  |
| M8.7.1 | Insert Functions in Plot Objects | NR | NR | NR | NR |  |
| M8.7.2 | OpenTrack Evaluation Files | PE | NR | NR | NR |  |
| M9.1 | File Commands: Menu Document | PE | NR | PE | NR |  |
| M9.2 | Print | NR | NR | NR | NR |  |
| M9.3 | Menu Info | NR | NR | NR | NR |  |
| M9.4 | Menu Edit | NR | NR | NR | NR |  |
| M9.5 | Menu Format | NR | NR | NR | NR |  |
| M9.6 | Menu Tools | NR | NR | NR | NR |  |
| M9.7 | Menu Functions | NR | NR | NR | NR |  |
| M9.7.1 | Functions →→→→ Labels | NR | NR | NR | NR |  |
| M9.8 | Data Exchange | NR | NR | NR | NR |  |
| R17.1 | Script Mode for OpenTrack (without Run-Files) | NR | NR | NR | NR |  |
| R17.2 | Script Mode for OpenTrack (with Run-Files) | PE | PE (1) | PE | NR |  |
| R17.3 | Expanded Context Menus | NR | NR | NR | NR |  |
| R17.4 | Export Preferences | NR | NR | NR | NR |  |
| R17.5 | Import Preferences | NR | NR | NR | NR |  |
| R17.6 | New Subselect Functions | NR | NR | NR | NR |  |
| R17.7 | New Attributes in multiple Selection of Routes | NR | NR | NR | NR |  |
| R17.8 | Review Kilometre Data | NR | NR | NR | NR |  |
| R17.9 | Extended Message Functions | NR | NR | NR | NR |  |
| R17.10 | New Finder Functionality | NR | NR | NR | NR |  |
| R17.11 | Train Acceleration Rule ("30-second rule") | PE | NR | PE | NR |  |
| R17.12 | Locomotive and Wagon Group Position within the Train | PE | NR | PE | NR |  |
| R17.13 | Curve Resistance: New Formulas and Percentage Factor | PE | NR | PE | NR |  |
| R17.14 | New Vertex Inspector Feature | NR | NR | NR | NR |  |
| R17.15 | New Train Category-Specific Signal Type | PE | NR | PE | NR |  |
| R17.16 | Coasting Dependent on Train Category | PE | NR | PE | NR |  |
| R17.17 | New Signal Attribute "Signal Name" | PE | NR | PE | NR |  |
| R17.18 | Extended Signal Attribute "Dispatching" | PE (1) | NR | PE (1) | NR |  |
| R17.19 | New Plotting Attributes | NR | NR | NR | NR |  |
| R17.20 | New Measuring Tool Functions | NR | NR | NR | NR |  |
| R17.21 | New Power Supply Element Plots and Output Data | NR | NR | NR | NR |  |
| R17.22 | New Itinerary Inspector Features | NR | NR | NR | NR |  |
| R17.23 | New Train Category Attributes | PE | NR | PE | NR |  |
| R17.24 | New Manual Scheduling of Individual Courses | NR | NR | NR | NR |  |
| R17.25 | New Incident Type "Train Tractive Effort" | PE | PE | PE | NR |  |
| R17.26 | New Incident Type "Signal / Group of Signals Headway" | PE | PE | PE | NR |  |
| R17.27 | New Incident Type "Signal Stop" | PE | PE | PE | NR |  |
| R17.28 | Changes to Timetable Window | PE | PE | PE | NR |  |
| R17.29 | Station Loading | NR | NR | NR | NR |  |
| R17.30 | Changes to Connection Definition | PE | PE | PE | NR |  |
| R17.31 | Day Offset for Interval Trains | PE | PE | PE | NR |  |
| R17.32 | Quick Assignment of Signal Aspects to Routes | PE | NR | PE | NR |  |
| R17.33 | Pathfinding | NR | NR | NR | NR |  |
| R17.34 | Deleting Multiple Paths | NR | NR | NR | NR |  |
| R17.35 | Automatically Calculate Kilometre Points | NR | NR | NR | NR |  |
| R17.36 | Create Measurement Instruments at Main Signals | NR | NR | NR | NR |  |
| R17.37 | Create Signal Name Labels | NR | NR | NR | NR |  |
| R17.38 | New Functions Submenu | NR | NR | NR | NR |  |
| R17.39 | Export and Import of incidents | NR | NR | NR | NR |  |
| R17.40 | Station Statistics | NR | NR | NR | NR |  |
| A01 | Complete discoverable stock-function Agent/MCP operation coverage | PE | NR | NR | NR | opentrack_generate_operations |
| A02 | Deliverable self-contained Skill and MCP distributions | PE | NR | NR | NR |  |
| A03 | Original native project/catalog import and export compatibility | PE | PE (1) | PE | PE |  |
| A04 | Atomic reversible data edits and complete reference preservation | PE | NR | PE (1) | PE |  |
| A05 | Schema/round-trip/static checks and targeted original compatibility acceptance | PE | PE (1) | PE (1) | NR |  |
| A06 | Optimized engine/formation/course/route/path/itinerary/timetable generation | PE | PE (3) | PE (1) | NR | opentrack_generate_operations |
| A07 | Original public functions mapped to typed Agent operations with explicit unsupported cases | PE | NR | NR | NR | opentrack_generate_operations |
| A08 | Original stock English OpenTrack baseline without localization or injected-enhancement assumptions | PE | NR | NR | NR |  |
| G01 | Generate engine records and full-range traction curves with explicit provenance | PE | PE (1) | PE | NR | opentrack_generate_operations |
| G02 | Generate train formations with exact engine references, positions and braking data | PE | PE (1) | PE | NR | opentrack_generate_operations |
| G03 | Generate routes from directed topology and signal boundaries | PE | PE (1) | PE | NR | opentrack_generate_operations |
| G04 | Generate continuous Paths and Itineraries with correct native identities/document references | PE | PE (1) | PE | NR | opentrack_generate_operations |
| G05 | Generate Courses/Services bound to valid formations and Itineraries | PE | PE (2) | PE | PE | opentrack_generate_operations |
| G06 | Generate ordered station timetable rows, dwell times and correct native dictionary keys | PE | PE (2) | PE | PE | opentrack_generate_operations |
| G07 | Generate repeated/bidirectional service patterns in bounded atomic batches | PE | PE | PE | NR | opentrack_generate_operations |
| G08 | Compact previews, actionable validation and source-preserving publication | PE | NR | NR | NR | opentrack_generate_operations |
| G09 | Executable Skill/MCP examples and original-only compatibility tests | PE | NR | NR | NR | opentrack_generate_operations |
| G10 | Verify generation throughput and avoid per-record Agent round trips | PE | NR | NR | NR | opentrack_generate_operations |
