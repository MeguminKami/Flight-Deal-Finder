'''
Airport dataset validator and updater utility.
Run this to check the integrity of airports.json.
'''
import json
from pathlib import Path
from collections import Counter


REQUIRED_FIELDS = ['iata', 'city', 'country', 'country_code', 'continent']
VALID_CONTINENTS = ['Europe', 'North America', 'South America', 'Asia', 'Africa', 'Oceania']


def validate_airports(file_path: str = 'airports.json'):
    '''Validate the airports dataset.'''
    print(f"Validating {file_path}...")

    if not Path(file_path).exists():
        print(f"❌ Error: {file_path} not found")
        return False

    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            airports = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON: {e}")
            return False

    if not isinstance(airports, list):
        print("❌ Error: Root element must be a list")
        return False

    errors = []
    warnings = []
    iata_codes = set()

    for idx, airport in enumerate(airports):
        if not isinstance(airport, dict):
            errors.append(f"Airport {idx}: Not a dictionary")
            continue

        for field in REQUIRED_FIELDS:
            if field not in airport:
                errors.append(f"Airport {idx}: Missing required field '{field}'")

        iata = airport.get('iata', '')
        if iata:
            if len(iata) != 3:
                errors.append(f"Airport {idx} ({iata}): IATA code must be 3 characters")
            elif not iata.isupper():
                warnings.append(f"Airport {idx} ({iata}): IATA code should be uppercase")

            if iata in iata_codes:
                errors.append(f"Airport {idx} ({iata}): Duplicate IATA code")
            else:
                iata_codes.add(iata)

        country_code = airport.get('country_code', '')
        if country_code and len(country_code) != 2:
            errors.append(f"Airport {idx} ({iata}): Country code must be 2 characters")

        continent = airport.get('continent', '')
        if continent and continent not in VALID_CONTINENTS:
            errors.append(
                f"Airport {idx} ({iata}): Invalid continent '{continent}'. "
                f"Must be one of: {', '.join(VALID_CONTINENTS)}"
            )

    print(f"\n📊 Statistics:")
    print(f"   Total airports: {len(airports)}")
    print(f"   Unique IATA codes: {len(iata_codes)}")

    if airports:
        continent_counts = Counter(a.get('continent', 'Unknown') for a in airports)
        print(f"\n🌍 Airports by continent:")
        for continent in sorted(continent_counts.keys()):
            print(f"   {continent}: {continent_counts[continent]}")

        country_counts = Counter(a.get('country', 'Unknown') for a in airports)
        print(f"\n🌐 Top countries:")
        for country, count in country_counts.most_common(10):
            print(f"   {country}: {count}")

    if errors:
        print(f"\n❌ Found {len(errors)} errors:")
        for error in errors[:20]:
            print(f"   - {error}")
        if len(errors) > 20:
            print(f"   ... and {len(errors) - 20} more")
        return False

    if warnings:
        print(f"\n⚠️  Found {len(warnings)} warnings:")
        for warning in warnings[:10]:
            print(f"   - {warning}")
        if len(warnings) > 10:
            print(f"   ... and {len(warnings) - 10} more")

    print("\n✅ Validation passed!")
    return True


def sort_airports(file_path: str = 'airports.json'):
    '''Sort airports by continent, then country, then city.'''
    print(f"\nSorting {file_path}...")

    with open(file_path, 'r', encoding='utf-8') as f:
        airports = json.load(f)

    airports.sort(key=lambda a: (
        a.get('continent', ''),
        a.get('country', ''),
        a.get('city', ''),
        a.get('iata', '')
    ))

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(airports, f, indent=2, ensure_ascii=False)

    print("✅ Airports sorted and saved")


def check_flag_emojis(file_path: str = 'airports.json'):
    '''Test flag emoji generation for all airports.'''
    print("\n🚩 Testing flag emoji generation...")

    with open(file_path, 'r', encoding='utf-8') as f:
        airports = json.load(f)

    for airport in airports[:10]:
        code = airport.get('country_code', '')
        iata = airport.get('iata', '')

        if code and len(code) == 2:
            code_points = [ord(char) + 127397 for char in code.upper()]
            flag = chr(code_points[0]) + chr(code_points[1])
            print(f"   {flag} {iata} - {airport.get('city', '')} ({code})")

    print("   ... (showing first 10)")


if __name__ == '__main__':
    import sys

    file_path = sys.argv[1] if len(sys.argv) > 1 else 'airports.json'

    if validate_airports(file_path):
        check_flag_emojis(file_path)

        response = input("\nSort airports alphabetically? (y/n): ")
        if response.lower() == 'y':
            sort_airports(file_path)
    else:
        print("\n⚠️  Please fix errors before proceeding")
        sys.exit(1)
