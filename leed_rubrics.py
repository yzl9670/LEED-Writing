# leed_rubrics.py

# LEED Table Data
LEED_TABLE_DATA = [
    # Location and Transportation
    {'section': 'Location and Transportation (9 Points)'},
    {'category': '', 'type': 'Credit', 'title': 'LEED for Neighborhood Development Location', 'points': 9},
    {'category': '', 'type': 'Credit', 'title': 'Sensitive Land Protection', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'High Priority Site and Equitable Development', 'points': 2},
    {'category': '', 'type': 'Credit', 'title': 'Surrounding Density and Diverse Uses', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Access to Quality Transit', 'points': 2},
    {'category': '', 'type': 'Credit', 'title': 'Bicycle Facilities', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Reduced Parking Footprint', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Electric Vehicles', 'points': 1},

    # Sustainable Sites
    {'section': 'Sustainable Sites (9 Points)'},
    {'category': '', 'type': 'Prereq', 'title': 'Construction Activity Pollution Prevention', 'points': None},
    {'category': '', 'type': 'Prereq', 'title': 'Environmental Site Assessment', 'points': None},
    {'category': '', 'type': 'Credit', 'title': 'Site Assessment', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Protect or Restore Habitat', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Open Space', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Rainwater Management', 'points': 2},
    {'category': '', 'type': 'Credit', 'title': 'Heat Island Reduction', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Light Pollution Reduction', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Places of Respite', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Direct Exterior Access', 'points': 1},

    # Water Efficiency
    {'section': 'Water Efficiency (11 Points)'},
    {'category': '', 'type': 'Prereq', 'title': 'Outdoor Water Use Reduction', 'points': None},
    {'category': '', 'type': 'Prereq', 'title': 'Indoor Water Use Reduction', 'points': None},
    {'category': '', 'type': 'Prereq', 'title': 'Building-Level Water Metering', 'points': None},
    {'category': '', 'type': 'Credit', 'title': 'Outdoor Water Use Reduction', 'points': 2},
    {'category': '', 'type': 'Credit', 'title': 'Indoor Water Use Reduction', 'points': 7},
    {'category': '', 'type': 'Credit', 'title': 'Optimize Process Water Use', 'points': 2},
    {'category': '', 'type': 'Credit', 'title': 'Water Metering', 'points': 2},

    # Energy and Atmosphere
    {'section': 'Energy and Atmosphere (35 Points)'},
    {'category': '', 'type': 'Prereq', 'title': 'Fundamental Commissioning and Verification', 'points': None},
    {'category': '', 'type': 'Prereq', 'title': 'Minimum Energy Performance', 'points': None},
    {'category': '', 'type': 'Prereq', 'title': 'Building-Level Energy Metering', 'points': None},
    {'category': '', 'type': 'Prereq', 'title': 'Fundamental Refrigerant Management', 'points': None},
    {'category': '', 'type': 'Credit', 'title': 'Enhanced Commissioning', 'points': 6},
    {'category': '', 'type': 'Credit', 'title': 'Optimize Energy Performance', 'points': 20},
    {'category': '', 'type': 'Credit', 'title': 'Advanced Energy Metering', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Grid Harmonization', 'points': 2},
    {'category': '', 'type': 'Credit', 'title': 'Renewable Energy', 'points': 3},
    {'category': '', 'type': 'Credit', 'title': 'Enhanced Refrigerant Management', 'points': 1},

    # Materials and Resources
    {'section': 'Materials and Resources (19 Points)'},
    {'category': '', 'type': 'Prereq', 'title': 'Storage and Collection of Recyclables', 'points': None},
    {'category': '', 'type': 'Prereq', 'title': 'PBT Source Reduction - Mercury', 'points': None},
    {'category': '', 'type': 'Credit', 'title': 'Building Life-Cycle Impact Reduction', 'points': 5},
    {'category': '', 'type': 'Credit', 'title': 'Environmental Product Declarations', 'points': 2},
    {'category': '', 'type': 'Credit', 'title': 'Sourcing of Raw Materials', 'points': 2},
    {'category': '', 'type': 'Credit', 'title': 'Material Ingredients', 'points': 2},
    {'category': '', 'type': 'Credit', 'title': 'PBT Source Reduction - Lead, Cadmium, and Copper', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Furniture and Medical Furnishings', 'points': 2},
    {'category': '', 'type': 'Credit', 'title': 'Design for Flexibility', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Construction and Demolition Waste Management', 'points': 2},

    # Indoor Environmental Quality
    {'section': 'Indoor Environmental Quality (16 Points)'},
    {'category': '', 'type': 'Prereq', 'title': 'Minimum Indoor Air Quality Performance', 'points': None},
    {'category': '', 'type': 'Prereq', 'title': 'Environmental Tobacco Smoke Control', 'points': None},
    {'category': '', 'type': 'Credit', 'title': 'Enhanced Indoor Air Quality Strategies', 'points': 2},
    {'category': '', 'type': 'Credit', 'title': 'Low-Emitting Materials', 'points': 3},
    {'category': '', 'type': 'Credit', 'title': 'Construction Indoor Air Quality Management Plan', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Indoor Air Quality Assessment', 'points': 2},
    {'category': '', 'type': 'Credit', 'title': 'Thermal Comfort', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Interior Lighting', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Daylight', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Quality Views', 'points': 2},
    {'category': '', 'type': 'Credit', 'title': 'Acoustic Performance', 'points': 2},

    # Innovation
    {'section': 'Innovation (6 Points)'},
    {'category': '', 'type': 'Credit', 'title': 'Innovation', 'points': 5},
    {'category': '', 'type': 'Credit', 'title': 'LEED Accredited Professional', 'points': 1},

    # Regional Priority
    {'section': 'Regional Priority (4 Points)'},
    {'category': '', 'type': 'Credit', 'title': 'Regional Priority: Specific Credit', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Regional Priority: Specific Credit', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Regional Priority: Specific Credit', 'points': 1},
    {'category': '', 'type': 'Credit', 'title': 'Regional Priority: Specific Credit', 'points': 1},

    # Totals
    {'section': 'TOTALS - Possible Points: 110'},
    {'section': 'Certified: 40 to 49 points, Silver: 50 to 59 points, Gold: 60 to 79 points, Platinum: 80 to 110'},
]

# LEED Rubrics
LEED_RUBRICS = {
    'LEED for Neighborhood Development Location': 'Rubric text for LEED for Neighborhood Development Location...',
    'Sensitive Land Protection': 'Rubric text for Sensitive Land Protection...',
    'High Priority Site and Equitable Development': 'Rubric text for High Priority Site and Equitable Development...',
    'Surrounding Density and Diverse Uses': 'Rubric text for Surrounding Density and Diverse Uses...',
    'Access to Quality Transit': 'Rubric text for Access to Quality Transit...',
    'Bicycle Facilities': 'Rubric text for Bicycle Facilities...',
    'Reduced Parking Footprint': 'Rubric text for Reduced Parking Footprint...',
    'Electric Vehicles': 'Rubric text for Electric Vehicles...',
    
    # Rubrics for Sustainable Sites
    'Construction Activity Pollution Prevention': 'Prerequisite - Required measures for controlling pollution...',
    'Environmental Site Assessment': 'Prerequisite - Required environmental site assessment...',
    'Site Assessment': 'Rubric text for Site Assessment...',
    'Protect or Restore Habitat': 'Rubric text for Protect or Restore Habitat...',
    'Open Space': 'Rubric text for Open Space...',
    'Rainwater Management': 'Rubric text for Rainwater Management...',
    'Heat Island Reduction': 'Rubric text for Heat Island Reduction...',
    'Light Pollution Reduction': 'Rubric text for Light Pollution Reduction...',
    'Places of Respite': 'Rubric text for Places of Respite...',
    'Direct Exterior Access': 'Rubric text for Direct Exterior Access...',

    # Rubrics for Water Efficiency
    'Outdoor Water Use Reduction': 'Prerequisite - Required measures for reducing outdoor water use...',
    'Indoor Water Use Reduction': 'Prerequisite - Required measures for reducing indoor water use...',
    'Building-Level Water Metering': 'Prerequisite - Required building-level water metering...',
    'Optimize Process Water Use': 'Rubric text for Optimize Process Water Use...',
    'Water Metering': 'Rubric text for Water Metering...',

    # Rubrics for Energy and Atmosphere
    'Fundamental Commissioning and Verification': 'Prerequisite - Required commissioning and verification...',
    'Minimum Energy Performance': 'Prerequisite - Required minimum energy performance...',
    'Building-Level Energy Metering': 'Prerequisite - Required building-level energy metering...',
    'Fundamental Refrigerant Management': 'Prerequisite - Required refrigerant management...',
    'Enhanced Commissioning': 'Rubric text for Enhanced Commissioning...',
    'Optimize Energy Performance': 'Rubric text for Optimize Energy Performance...',
    'Advanced Energy Metering': 'Rubric text for Advanced Energy Metering...',
    'Grid Harmonization': 'Rubric text for Grid Harmonization...',
    'Renewable Energy': 'Rubric text for Renewable Energy...',
    'Enhanced Refrigerant Management': 'Rubric text for Enhanced Refrigerant Management...',

    # Rubrics for Materials and Resources
    'Storage and Collection of Recyclables': 'Prerequisite - Required storage and collection of recyclables...',
    'PBT Source Reduction - Mercury': 'Prerequisite - Required source reduction for mercury...',
    'Building Life-Cycle Impact Reduction': 'Rubric text for Building Life-Cycle Impact Reduction...',
    'Environmental Product Declarations': 'Rubric text for Environmental Product Declarations...',
    'Sourcing of Raw Materials': 'Rubric text for Sourcing of Raw Materials...',
    'Material Ingredients': 'Rubric text for Material Ingredients...',
    'PBT Source Reduction - Lead, Cadmium, and Copper': 'Rubric text for PBT Source Reduction - Lead, Cadmium, and Copper...',
    'Furniture and Medical Furnishings': 'Rubric text for Furniture and Medical Furnishings...',
    'Design for Flexibility': 'Rubric text for Design for Flexibility...',
    'Construction and Demolition Waste Management': 'Rubric text for Construction and Demolition Waste Management...',

    # Rubrics for Indoor Environmental Quality
    'Minimum Indoor Air Quality Performance': 'Prerequisite - Required minimum indoor air quality...',
    'Environmental Tobacco Smoke Control': 'Prerequisite - Required tobacco smoke control...',
    'Enhanced Indoor Air Quality Strategies': 'Rubric text for Enhanced Indoor Air Quality Strategies...',
    'Low-Emitting Materials': 'Rubric text for Low-Emitting Materials...',
    'Construction Indoor Air Quality Management Plan': 'Rubric text for Construction Indoor Air Quality Management Plan...',
    'Indoor Air Quality Assessment': 'Rubric text for Indoor Air Quality Assessment...',
    'Thermal Comfort': 'Rubric text for Thermal Comfort...',
    'Interior Lighting': 'Rubric text for Interior Lighting...',
    'Daylight': 'Rubric text for Daylight...',
    'Quality Views': 'Rubric text for Quality Views...',
    'Acoustic Performance': 'Rubric text for Acoustic Performance...',

    # Rubrics for Innovation
    'Innovation': 'Rubric text for Innovation...',
    'LEED Accredited Professional': 'Rubric text for LEED Accredited Professional...',

    # Rubrics for Regional Priority
    'Regional Priority: Specific Credit': 'Rubric text for Regional Priority: Specific Credit...'
}

# Note:
# Please ensure that you fill in the actual rubric texts for each LEED credit and prerequisite.
# The above entries are placeholders to illustrate the structure.
