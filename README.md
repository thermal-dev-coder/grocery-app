# Grocery App (Rafa)

App web para gestionar compras de supermercado con foco móvil.

## Objetivo
- Importar compras históricas desde CSV (Fry's y Sprouts)
- Consolidar catálogo de productos en SQLite
- Enriquecer productos con imágenes
- Publicar dashboard simple en Firebase Hosting

## Estado actual
- Productos: **417**
- Compras importadas: **421**
- Cobertura de imágenes: **220 / 417**
- Sitio publicado: <https://rafa-grocery-app-2026-73dad.web.app>

## Estructura
- `data/grocery.db` → base SQLite
- `scripts/import_grocery_csv.py` → importador CSV
- `scripts/enrich_product_images.py` → enriquecimiento de imágenes
- `public/index.html` + `public/data.json` → dashboard estático
- `firebase.json` + `.firebaserc` → despliegue Hosting

## Flujo de trabajo
1. Importar CSV:
   ```bash
   python3 scripts/import_grocery_csv.py --csv <archivo.csv> --store <frys|sprouts> --db data/grocery.db
   ```
2. Buscar imágenes:
   ```bash
   python3 scripts/enrich_product_images.py --db data/grocery.db --limit 25 --sleep-ms 0
   ```
3. Regenerar dataset web (data.json) desde SQLite
4. Deploy a Firebase Hosting

## Deploy
```bash
npx firebase-tools deploy --only hosting --project rafa-grocery-app-2026-73dad --token "$FIREBASE_TOKEN"
```
