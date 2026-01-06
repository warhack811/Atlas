# Quick script to generate allowed predicates list for prompt
import sys
sys.path.insert(0, ".")

from Atlas.memory.predicate_catalog import get_catalog

catalog = get_catalog()
if catalog:
    enabled = catalog.get_enabled_predicates()
    print("\n".join(enabled))
else:
    print("Catalog failed to load")
