"""
GhanaHammer Initial Data Setup
Run this in Django shell after migrations:
  python manage.py shell
  >>> exec(open('setup_data.py').read())
  >>> create_initial_data()
"""

def create_initial_data():
    from apps.gh_auctions.models import Category
    from apps.bidding.models import BidCreditPackage

    print("Creating categories...")
    categories = [
        # (name, slug, icon, parent_name)
        ('Vehicles', 'vehicles', 'bi-car-front', None),
        ('Cars & SUVs', 'cars-suvs', 'bi-car-front-fill', 'Vehicles'),
        ('Trucks & Vans', 'trucks-vans', 'bi-truck', 'Vehicles'),
        ('Motorcycles', 'motorcycles', 'bi-bicycle', 'Vehicles'),
        ('Buses & Minibuses', 'buses', 'bi-bus-front', 'Vehicles'),
        ('Tractors & Farm Equipment', 'tractors', 'bi-gear', 'Vehicles'),
        ('Boats & Watercraft', 'boats', 'bi-water', 'Vehicles'),

        ('Property & Real Estate', 'property', 'bi-house', None),
        ('Houses & Villas', 'houses', 'bi-house-fill', 'Property & Real Estate'),
        ('Land & Plots', 'land', 'bi-map', 'Property & Real Estate'),
        ('Commercial Property', 'commercial-property', 'bi-building', 'Property & Real Estate'),
        ('Apartments & Flats', 'apartments', 'bi-buildings', 'Property & Real Estate'),

        ('Electronics', 'electronics', 'bi-cpu', None),
        ('Phones & Tablets', 'phones-tablets', 'bi-phone', 'Electronics'),
        ('Computers & Laptops', 'computers', 'bi-laptop', 'Electronics'),
        ('TVs & Appliances', 'tvs-appliances', 'bi-tv', 'Electronics'),
        ('Audio & Cameras', 'audio-cameras', 'bi-camera', 'Electronics'),

        ('Livestock & Agriculture', 'livestock', 'bi-tree', None),
        ('Cattle & Cows', 'cattle', 'bi-tree-fill', 'Livestock & Agriculture'),
        ('Poultry', 'poultry', 'bi-egg', 'Livestock & Agriculture'),
        ('Goats & Sheep', 'goats-sheep', 'bi-tree', 'Livestock & Agriculture'),
        ('Farm Produce', 'farm-produce', 'bi-basket', 'Livestock & Agriculture'),

        ('Art & Collectibles', 'art', 'bi-palette', None),
        ('Paintings & Sculptures', 'paintings', 'bi-palette2', 'Art & Collectibles'),
        ('Antiques', 'antiques', 'bi-hourglass', 'Art & Collectibles'),
        ('Coins & Currency', 'coins', 'bi-coin', 'Art & Collectibles'),

        ('Government Surplus', 'government-surplus', 'bi-bank', None),
        ('Office Furniture', 'office-furniture', 'bi-briefcase', 'Government Surplus'),
        ('Industrial Equipment', 'industrial', 'bi-gear-wide', 'Government Surplus'),

        ('Fashion & Apparel', 'fashion', 'bi-bag', None),
        ('Jewellery & Watches', 'jewellery', 'bi-gem', None),
        ('Books & Media', 'books', 'bi-book', None),
        ('Sports & Fitness', 'sports', 'bi-trophy', None),
        ('Home & Garden', 'home-garden', 'bi-house-heart', None),
        ('Business Equipment', 'business-equipment', 'bi-printer', None),
        ('Heavy Machinery', 'machinery', 'bi-tools', None),
    ]

    parent_map = {}
    for name, slug, icon, parent_name in categories:
        parent = parent_map.get(parent_name) if parent_name else None
        cat, created = Category.objects.get_or_create(
            slug=slug,
            defaults={
                'name': name,
                'icon': icon,
                'parent': parent,
                'is_active': True,
            }
        )
        parent_map[name] = cat
        if created:
            print(f"  ✓ Created: {name}")
        else:
            print(f"  - Exists: {name}")

    print("\nCreating bid credit packages...")
    packages = [
        ('Starter Pack', 50, 49.00, 0),
        ('Value Pack', 150, 120.00, 20),
        ('Power Pack', 500, 350.00, 100),
        ('Mega Pack', 1000, 600.00, 250),
    ]
    for name, credits, price, bonus in packages:
        pkg, created = BidCreditPackage.objects.get_or_create(
            name=name,
            defaults={
                'credits': credits,
                'price_ghs': price,
                'bonus_credits': bonus,
                'is_active': True,
            }
        )
        if created:
            print(f"  ✓ Created: {name} ({credits}+{bonus} credits for GHS {price})")

    print("\n✅ Initial data setup complete!")
    print(f"   Categories created: {Category.objects.count()}")
    print(f"   Credit packages: {BidCreditPackage.objects.count()}")


if __name__ == '__main__':
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auction_platform.settings.development')
    django.setup()
    create_initial_data()
