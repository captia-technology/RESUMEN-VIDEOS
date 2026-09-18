## Qué cambia y por qué

<!-- Resumen breve del cambio y del motivo. Enlaza la incidencia si existe. -->

## Pruebas ejecutadas

Marca lo que hayas ejecutado y describe lo que no pudiste comprobar.

- [ ] `python3 -B -m unittest discover -s tests`
- [ ] `python3 -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"` (requiere FFmpeg)
- [ ] `claude plugin validate plugins/resumir-video --strict` y `claude plugin validate . --strict`
- [ ] Validadores de Codex: `validate_plugin.py` y `quick_validate.py`
- [ ] Prueba manual: <!-- cliente, versión, sistema operativo y qué se comprobó -->

No comprobado: <!-- qué queda pendiente de evidencia -->

## Documentación

- [ ] Actualizada la documentación afectada: <!-- indica qué documento -->
- [ ] No hace falta: <!-- motivo -->

## Versión

- [ ] No procede (el cambio no se publica como versión nueva)
- [ ] Versión actualizada en todos los archivos que enumera [CONTRIBUTING.md](https://github.com/captia-technology/RESUMEN-VIDEOS/blob/main/CONTRIBUTING.md#publicar-una-versión) y entrada añadida en `CHANGELOG.md`

## Confirmaciones

- [ ] El cambio no añade rutas locales, nombres de clientes, datos de trabajos reales ni material confidencial.
- [ ] La skill sigue siendo la única copia, autocontenida y válida para cualquier agente.
