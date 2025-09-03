# LEED Table Data
LEED_TABLE_DATA = [
    # Location and Transportation
    {
        'section': 'Location and Transportation (16 Points)',
        'items': [
            {'type': 'Credit', 'name': 'LEED for Neighborhood Development Location', 'points': 16},
            {'type': 'Credit', 'name': 'Sensitive Land Protection', 'points': 1},
            {'type': 'Credit', 'name': 'High Priority Site and Equitable Development', 'points': 2},
            {'type': 'Credit', 'name': 'Surrounding Density and Diverse Uses', 'points': 5},
            {'type': 'Credit', 'name': 'Access to Quality Transit', 'points': 5},
            {'type': 'Credit', 'name': 'Bicycle Facilities', 'points': 1},
            {'type': 'Credit', 'name': 'Reduced Parking Footprint', 'points': 1},
            {'type': 'Credit', 'name': 'Electric Vehicles', 'points': 1},
        ]
    },

    # Sustainable Sites
    {
        'section': 'Sustainable Sites (9 Points)',
        'items': [
            {'type': 'Prereq', 'name': 'Construction Activity Pollution Prevention', 'points': None},
            {'type': 'Credit', 'name': 'Site Assessment', 'points': 1},
            {'type': 'Credit', 'name': 'Protect or Restore Habitat', 'points': 1},
            {'type': 'Credit', 'name': 'Open Space', 'points': 1},
            {'type': 'Credit', 'name': 'Rainwater Management', 'points': 3},
            {'type': 'Credit', 'name': 'Heat Island Reduction', 'points': 2},
            {'type': 'Credit', 'name': 'Light Pollution Reduction', 'points': 1},
        ]
    },

    # Water Efficiency
    {
        'section': 'Water Efficiency (11 Points)',
        'items': [
            {'type': 'Prereq', 'name': 'Outdoor Water Use Reduction', 'points': None},
            {'type': 'Prereq', 'name': 'Indoor Water Use Reduction', 'points': None},
            {'type': 'Prereq', 'name': 'Building-Level Water Metering', 'points': None},
            {'type': 'Credit', 'name': 'Outdoor Water Use Reduction', 'points': 2},
            {'type': 'Credit', 'name': 'Indoor Water Use Reduction', 'points': 6},
            {'type': 'Credit', 'name': 'Optimize Process Water Use', 'points': 2},
            {'type': 'Credit', 'name': 'Water Metering', 'points': 1},
        ]
    },

    # Energy and Atmosphere
    {
        'section': 'Energy and Atmosphere (33 Points)',
        'items': [
            {'type': 'Prereq', 'name': 'Fundamental Commissioning and Verification', 'points': None},
            {'type': 'Prereq', 'name': 'Minimum Energy Performance', 'points': None},
            {'type': 'Prereq', 'name': 'Building-Level Energy Metering', 'points': None},
            {'type': 'Prereq', 'name': 'Fundamental Refrigerant Management', 'points': None},
            {'type': 'Credit', 'name': 'Enhanced Commissioning', 'points': 6},
            {'type': 'Credit', 'name': 'Optimize Energy Performance', 'points': 18},
            {'type': 'Credit', 'name': 'Advanced Energy Metering', 'points': 1},
            {'type': 'Credit', 'name': 'Grid Harmonization', 'points': 2},
            {'type': 'Credit', 'name': 'Renewable Energy', 'points': 5},
            {'type': 'Credit', 'name': 'Enhanced Refrigerant Management', 'points': 1},
        ]
    },

    # Materials and Resources
    {
        'section': 'Materials and Resources (13 Points)',
        'items': [
            {'type': 'Prereq', 'name': 'Storage and Collection of Recyclables', 'points': None},
            {'type': 'Credit', 'name': 'Building Life-Cycle Impact Reduction', 'points': 5},
            {'type': 'Credit', 'name': 'Environmental Product Declarations', 'points': 2},
            {'type': 'Credit', 'name': 'Sourcing of Raw Materials', 'points': 2},
            {'type': 'Credit', 'name': 'Material Ingredients', 'points': 2},
            {'type': 'Credit', 'name': 'Construction and Demolition Waste Management', 'points': 2},
        ]
    },

    # Indoor Environmental Quality
    {
        'section': 'Indoor Environmental Quality (16 Points)',
        'items': [
            {'type': 'Prereq', 'name': 'Minimum Indoor Air Quality Performance', 'points': None},
            {'type': 'Prereq', 'name': 'Environmental Tobacco Smoke Control', 'points': None},
            {'type': 'Credit', 'name': 'Enhanced Indoor Air Quality Strategies', 'points': 2},
            {'type': 'Credit', 'name': 'Low-Emitting Materials', 'points': 3},
            {'type': 'Credit', 'name': 'Construction Indoor Air Quality Management Plan', 'points': 1},
            {'type': 'Credit', 'name': 'Indoor Air Quality Assessment', 'points': 2},
            {'type': 'Credit', 'name': 'Thermal Comfort', 'points': 1},
            {'type': 'Credit', 'name': 'Interior Lighting', 'points': 2},
            {'type': 'Credit', 'name': 'Daylight', 'points': 3},
            {'type': 'Credit', 'name': 'Quality Views', 'points': 1},
            {'type': 'Credit', 'name': 'Acoustic Performance', 'points': 1},
        ]
    },

    # Innovation
    {
        'section': 'Innovation (6 Points)',
        'items': [
            {'type': 'Credit', 'name': 'Innovation', 'points': 5},
            {'type': 'Credit', 'name': 'LEED Accredited Professional', 'points': 1},
        ]
    },

    # Regional Priority
    {
        'section': 'Regional Priority (4 Points)',
        'items': [
            {'type': 'Credit', 'name': 'Regional Priority: Specific Credit 1', 'points': 1},
            {'type': 'Credit', 'name': 'Regional Priority: Specific Credit 2', 'points': 1},
            {'type': 'Credit', 'name': 'Regional Priority: Specific Credit 3', 'points': 1},
            {'type': 'Credit', 'name': 'Regional Priority: Specific Credit 4', 'points': 1},
        ]
    },
]