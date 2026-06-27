# Archive Workflow

Use this reference when a Ren'Py game ships `.rpa` archives, lacks source `.rpy` files, or contains archived legacy translations.

## Detect Archive State

Run fast discovery from the game root:

```powershell
rg --files game | rg "\.(rpa|rpy|rpyc)$"
```

If source `.rpy` files are absent or incomplete, inspect archive contents before generating translations. Archived `tl/chinese/*.rpyc` can cause Ren'Py to think a translation already exists, even when the on-disk `game/tl/chinese` folder is missing or broken.

Use the bundled script:

```powershell
python <skill>/scripts/extract_rpa.py game/scripts.rpa --output game --suffix .rpyc
```

Then decompile `.rpyc` with the project's available decompiler/UNREN workflow if needed. Prefer editing generated `game/tl/<language>/*.rpy`, not original story scripts.

## Polluted Legacy Translations

Treat a legacy translation as polluted when any of these are true:

- `game/tl/chinese` contains mojibake, broken tags, or syntactically invalid `.rpy`.
- `scripts.rpa` contains `tl/chinese/*.rpyc` from an old fan translation.
- Ren'Py `translate chinese` generates very few files despite a large untranslated game.
- Lint reports errors under `tl/chinese/*.rpyc` that do not exist on disk.

When polluted:

1. Back up or move the bad `game/tl/chinese` folder.
2. Generate a clean language such as `schinese`:

   ```powershell
   renpy translate schinese --empty
   ```

3. Add a late language override, for example:

   ```renpy
   init 10 python:
       config.language = "schinese"
   ```

4. Translate and validate `game/tl/schinese`.
5. Only after validation, remove or repack away the bad legacy layer if the user wants a clean game.

## Repacking Archives

Use repacking only after validation and only for conflicting legacy paths. Do not repack image/movie/audio archives merely for localization cleanup.

```powershell
python <skill>/scripts/repack_rpa_without_paths.py game/scripts.rpa --skip-prefix tl/chinese/ --backup-dir localization_backups/scripts_rpa_before_cleanup
```

After repacking, verify the archive index contains no removed prefix, then run Ren'Py lint again. A clean result should no longer mention the removed legacy language in statistics or tag errors.
