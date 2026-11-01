# Third-party resources

The MIT license applies to the project's original source code and documentation.
It does not grant rights to Tencent/Riot game artwork, trademarks, game screenshots,
MuMu's SDK, or the separately licensed dependencies and OCR models.

| Resource | Source / ownership | Use |
| --- | --- | --- |
| Game portraits and screenshots under `assets/` and `tests/fixtures/` | 金铲铲之战 / Teamfight Tactics, Tencent / Riot Games; screenshots supplied during development | Small recognition templates and offline regression fixtures |
| Desktop game icon | [Official site image](https://game.gtimg.cn/images/jk/logo-jcc.png) | Local desktop shortcut icon, converted to ICO |
| Public portrait metadata and artwork | [CommunityDragon](https://communitydragon.org/docs/assets), [Riot Data Dragon](https://developer.riotgames.com/docs/tft) | Downloaded by the resource tools; full downloaded libraries are not committed |
| JCC official roster and portraits | [Tencent version index](https://game.gtimg.cn/images/lol/act/jkzlk/js/config/versiondataconfig.js) | Downloaded by the S16 updater |
| MuMu external renderer SDK | Installed with MuMu Player | Loaded from the user's own emulator installation; DLLs are not distributed |
| OCR runtime and models | [RapidOCR](https://github.com/RapidAI/RapidOCR), ONNX Runtime and their dependencies | Installed separately through Python requirements |

Fixture catalog entries retain their original source URLs/version metadata when
available. Runtime screenshots used as fixtures have unrelated gameplay/player
areas removed. Downloaded assets and model files retain their upstream terms.

This is an independent project and is not an official Tencent, Riot Games, or
MuMu product.
