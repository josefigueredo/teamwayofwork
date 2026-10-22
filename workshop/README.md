# Episodio del taller

Esta carpeta tiene el episodio de esta skill en el taller de skills de team. Se mantiene acá, al lado de la skill: si un cambio en la skill vuelve viejo lo que muestra el episodio, el episodio se actualiza en el mismo PR.

- `episodes/<serie>/NN-<id>.json`: el guion. El formato está en `docs/guion.md` del repo del taller (`skills-workshop`).
- `episodes/pages/`: las páginas reales que muestra el episodio, si las tiene.
- `dist/`: el sitio armado (`index.html`, la página de la serie y `control.html` para presentar). Se commitea junto con el guion.

## Cómo se edita

1. Editás el guion en `episodes/`.
2. Lo armás con el motor del taller, que tenés que tener clonado (por ejemplo, al lado de este repo):

   ```
   python3 <taller>/build.py --root workshop validate
   python3 <taller>/build.py --root workshop build
   ```

   `build` valida el guion, revisa la privacidad y recién ahí escribe `dist/`. Si cambiaste un paso `real`, primero volvé a capturarlo con `python3 <taller>/build.py --root workshop capture --episode <id>`.
3. Commiteás `episodes/` y `dist/` juntos.
4. En el repo del taller, `python3 build.py sync` trae el guion a su copia, que es la que arma las series completas. `python3 build.py sync --check` avisa si alguna skill quedó distinta de la copia o si su `dist/` quedó viejo.

## Cómo se publica

`.github/workflows/workshop-pages.yml` publica `dist/` en GitHub Pages en cada push a `main` que toque esta carpeta. No arma nada: primero comprueba que `dist/` salió del guion actual (`dist/source.sha256`) y, si no, falla y no publica nada viejo.

La primera vez hay que elegir **GitHub Actions** como fuente en Settings → Pages.
