# JPLAY и ESOTERIC Sound Stream: домены Music

Проверено 18 ноября 2026 года. Правила редактируются в `music-domain.list`,
готовый файл — `ruleset/music-domain.mrs`, провайдер — `music@domain`.
Шаблон `+.example.com` включает сам домен и его поддомены.

Это список по публичным источникам, а не запись сетевого трафика приложений.
Наличие интеграции подтверждает сервис, но не доказывает, что приложение
обращается к каждому его поддомену.

## Добавленные домены

| Домен | Назначение и основание |
| --- | --- |
| `jplay.app` | Официальный сайт JPLAY, руководство и поддержка: [сайт](https://jplay.app/), [описание работы](https://jplay.app/how-jplay-works). Конкретный отдельный backend не опубликован. |
| `jplay.eu` | Связанный официальный сайт JPLAY, на который ссылается [jplay.app](https://jplay.app/). Это домен продукта и поддержки; зависимость мобильного приложения при воспроизведении не установлена. |
| `esoteric.jp` | Официальный сайт, документация и загрузки ESOTERIC: [Sound Stream](https://www.esoteric.jp/en/product/sound_stream/top), [Google Play](https://play.google.com/store/apps/details?id=com.esoteric.EsotericSoundStream). Не подтверждён как адрес сервера обновления NET firmware. |
| `highresaudio.com` | Интегрированный в JPLAY сервис HIGHRESAUDIO, включая VirtualVault: [JPLAY](https://jplay.app/how-jplay-works), [история версий приложения](https://apps.apple.com/us/app/jplay/id1608773457). |
| `tunein.com` | Интернет-радио в экосистеме ESOTERIC: [официальное объявление производителя](https://www.esoteric.jp/en/support/news/327). |
| `radiotime.com` | Семейство адресов TuneIn; официальный [AIR API](https://tunein.com/broadcasters/api/) использует `air.radiotime.com`. Это подтверждение принадлежности сервису, а не наблюдение вызова AIR из Sound Stream. |
| `wikipedia.org` | Биографии исполнителей и описания альбомов JPLAY: [объявление разработчика](https://forum.minimserver.com/showthread.php?pid=54911&tid=7862). Суффикс покрывает языковые поддомены; точный API-хост не опубликован. |
| `tidalhifi.com`, `wimpmusic.com` | Дополнительные, в том числе исторические, домены TIDAL из [исходного списка v2fly](https://github.com/v2fly/domain-list-community/blob/master/data/tidal). Их использование текущими версиями JPLAY/Sound Stream отдельно не проверено. |
| `tidal-cms.s3.amazonaws.com` | Выделенный адрес контента TIDAL из [исходного списка blackmatrix7](https://github.com/blackmatrix7/ios_rule_script/blob/master/rule/Clash/TIDAL/TIDAL.list). Не означает маршрутизацию всего Amazon S3. |

## Уже покрыто

`qobuz.com`, `qobuz.io`, выделенные Qobuz CDN, `tidal.com` и
`radioparadise.com` уже присутствовали в Music. Интеграции Qobuz/TIDAL
подтверждены [JPLAY](https://jplay.app/how-jplay-works) и
[историей версий Sound Stream](https://apps.apple.com/us/app/esoteric-sound-stream/id1087231964).
Spotify в актуальном конфиге направлен в ту же группу Music отдельным
провайдером `spotify@domain`.

## Границы покрытия

- JPLAY официально представлен для iPhone, iPad и Mac; версия Android
  в проверенных официальных источниках не найдена. Sound Stream доступен
  для [Android](https://play.google.com/store/apps/details?id=com.esoteric.EsotericSoundStream)
  и [iOS](https://apps.apple.com/us/app/esoteric-sound-stream/id1087231964).
- Доменные правила действуют для всех обращений к указанному домену,
  независимо от приложения. Например, Wikipedia в браузере также попадёт
  в Music, если раньше не сработает другое правило.
- Радиостанции TuneIn могут отдавать звук со своих доменов. Их адреса
  зависят от выбранной станции; полный перечень здесь не установлен.
- Отдельные серверы лицензирования, обновлений прошивки и динамические CDN,
  не раскрытые публично, требуют проверки по журналу соединений устройств.
  Общие домены Apple/Google/Amazon, предполагаемые серверы LUMIN и домены
  только из email-адресов разработчиков не добавлялись.
- Локальное обнаружение устройств и UPnP/OpenHome работают в домашней сети.
  Они не требуют направления локальных адресов в Music. Ранние правила
  Adblock продолжают действовать для рекламных и аналитических поддоменов.
