#ayase

ayaseは、twitter botと見せかけたMojolicious::Liteアプリケーションです。

Mojolicious::Liteにおける標準的な手法を模索しています。

* 暗号化クッキーのためのパスフレーズの設定
* .htcをサーブするためのMIMEタイプ設定（app->types->type( htc => 'text/x-component'); ）
* リバースプロキシでサブディレクトリに接続する際のhookによるパス置換
* Mojolicious組み込みのUserAgentでWebコンテンツ取得
* メモリ内データの画像としての出力（$self->render_data( $bin,  format => 'jpeg');）
* AJAX通信用JSON生成（GET/POST）

##files

設置者が自分で準備し書き換える必要があるファイルは以下の通りです。

* /twitter_keys.yaml : Twitter APIで使うconsumer_keyのペア、access_tokenのペア

botとして動かすため設置者が書き換える必要があるファイルは以下の通りです。

* /index.cgi.conf : 設定ファイル
* /public/ayase.json : キャラクターが喋る台詞ファイル
* /public/ng.json : TweetしないTwitter IDリスト

##設置例

* http://mamesibori.net/ayase/

##changes

* ver 0.0.2 HTML5 Valid / Change xFolk to hAtom / Modify Templates
* ver 0.0.1 first import
