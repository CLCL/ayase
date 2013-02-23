#!/usr/bin/perl

use 5.010; # Mojolicious 1.9.8以降はPerl 5.10対応
use version; our $VERSION = qv('0.0.2');
use Mojolicious::Lite;
use utf8;
use Imager; # Image::Magickはオンメモリの画像操作が出来ない
use JSON -support_by_pp; # Mojo::JSONはGoogleのJSONはParseできない
use Net::Twitter 4.0000001; # Twitter API version 1.1対応版
use Date::Parse;
use DateTime::Format::HTTP;
use String::Random;
use YAML;

$ENV{MOJO_REVERSE_PROXY} = 1;
my $config = plugin 'Config'; 
# consumer_keyなど読込はdebugモードのエラー画面でstashに乗っかるのでダメ
my $keys = YAML::LoadFile( app->home->rel_file('twitter_keys.yaml') );
# index.cgiと同じディレクトリにtwitter_keys.yaml ファイルを以下の形式で置いておく
# キーは自分で取得する必要がある。
# "consumer_key" : 'aaaaaaaaaaaaaaaaaaa'
# "consumer_key_secret" : 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
# "access_token"        : 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
# "access_token_secret" : 'yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy'

# Net::Twitter初期化
my $nt  = Net::Twitter->new(
  traits => [qw/API::RESTv1_1 WrapError/],
  consumer_key        => $keys->{consumer_key},
  consumer_secret     => $keys->{consumer_key_secret},
  access_token        => $keys->{access_token},
  access_token_secret => $keys->{access_token_secret},
  ssl => 1,
);

app->secret($keys->{consumer_key}); # アプリ固有の暗号キーをTwitterのKey流用
app->types->type( htc => 'text/x-component'); # HTCファイルのMIME Type設定

# ディスパッチャの修正
# Apacheのmod_proxyで、Apacheとリバースプロキシで接続する場合
# Mojolicious::Lite アプルケーションが /docroot/ayase/index.cgi
# でmorbo index.cgiを実行すると、http://localhost:3000/ で
# サービスが提供される。一方、Apacheのmod_proxyで
# http://example.com/ayase を http://localhost:3000 に接続した
# 場合、サービスには URLにayase/ を追加したHTMLを吐いてもらわない
# と不整合になる。そこで、before_dispatchにhookかけて、アプリの
# 設置ディレクトリ ayase/ を付加します。
app->hook( before_dispatch => sub {
  my $self = shift;
  my $use_prefix
    = $self->req->headers->header('X-ProxyPassReverse-UsePrefix');
  if (defined $use_prefix && lc $use_prefix eq 'on') { # httpd.confでフラグ付けておきます
    my $prefix = 'ayase';  # 設置ディレクトリ /DocRoot/ayase
    #$self->req->url->base->path->parse($prefix);
    push @{$self->req->url->base->path->parts}, $prefix;
  }
});


# ROOT
get '/' => sub {
  my $self = shift;
  my $screenname = $self->session->{screenname};
  my $csrftoken;
  #  CSRFトークン
  unless ( $csrftoken = $self->session('csrftoken') ) {
    $csrftoken = String::Random::random_regex("[a-zA-Z0-9_]{32}");
    # CSRFトークンをセッションに保存
    $self->session( csrftoken => $csrftoken );
  }
  # テンプレートに可変値を渡す
  $self->stash( screenname => $screenname );
  $self->stash( csrftoken  => $csrftoken  );
} => 'index';

# 発言編集ページ
get '/edit' => sub {
  my $self = shift;
  my $csrftoken;
  #  CSRFトークン
  unless ( $csrftoken = $self->session('csrftoken') ) {
    $csrftoken = String::Random::random_regex("[a-zA-Z0-9_]{32}");
    # CSRFトークンをセッションに保存
    $self->session( csrftoken => $csrftoken );
  }
  # テンプレートに可変値を渡す
  $self->stash( csrftoken  => $csrftoken  );
}=> 'edit';

# 開発ページ（ペラページ）
get '/development' => 'development';

# キャラクター画像生成（image/jpeg）
get '/ayaseimg' => sub {
  my $self = shift;
  # ドル円レート取得
  my $json = JSON->new;
  #$LWP::Simple::ua->
  my $str  = $self->ua
             ->name("ayase/$VERSION ($^O) Mojolicious (Perl)") # User-Agent名
             ->get('http://www.google.com/ig/calculator?hl=en&q=1JPY=?USD')
             ->res->body or die $!;
  my $data = $json->allow_barekey->decode( $str ); # GoogleのJSONはこれで解析
  (my $rate = $data->{rhs} ) =~ s{\s.+}{};

  # 画像を作る
  my $img = Imager->new;
  my $ayasebasefile = app->home->rel_file('/public/images/ayase_base.png');
  $img->read( 
    file => $ayasebasefile, 
    type => 'png', 
  ) or die $img->errstr();
  my $s = sprintf('$%0.2f', $rate * 450 );
  my $font = Imager::Font->new(
    file => '/usr/share/fonts/ipa-pgothic/ipagp.ttf', #CentOS 6だとここ
  ) or die $img->errstr();
  # 価格表示（バックの白影）
  my $setting = {
    font => $font, size => '36', 
    utf8 => '1', 
    string => $s,
    x => '230',
    y => '150',
    color => '#ffffff', 
    aa => 1, # アンチエイリアス 
  };
  $img->string( %$setting ) or die $img->errstr();
  # 価格表示（前景の黒文字）
  $setting->{x} -= 2;
  $setting->{y} -= 2;
  $img->string( %$setting, color => 'black',) or die $img->errstr();
  my $bin;
  $img->write( data => \$bin, type => 'jpeg' ) or die $img->errstr();

  # JPEG画像としてメモリから画像を出力
  $self->render_data( $bin,  format => 'jpeg');
};

# list処理（application/json）
get '/list' => sub {
  my $self = shift;
  my $res = $nt->user_timeline({count => 200}); # ページャーは未実装
  # Twitter APIからの出力をそのまま渡すとモバイル端末には厳しい
  # 転量量になるので必要最低限の要素だけに厳選します。
  my $res2;
  foreach my $item ( @$res ) {
    # Twitterの時刻出力をJavaScript用時刻文字列に変換
    my $dt = DateTime->from_epoch(
      time_zone => 'Asia/Tokyo',
      epoch     => str2time( $item->{created_at} ),
    );
    # Twitter APIのJSON出力に似せた構造体を作る
    unshift @$res2, {
      id          => $item->{id} + 0,
      id_str      => qq($item->{id}),
      created_at  => DateTime::Format::HTTP->format_datetime( $dt ),
      text        => $item->{text},
      in_reply_to_screen_name => $item->{in_reply_to_screen_name},
      user => { screen_name => $item->{user}->{screen_name},
                name        => $item->{user}->{name},
                profile_image_url_https => $item->{user}->{profile_image_url_https},
              },
    };
  }
  $self->render( json => { http_message => $nt->http_message, 
                           status       => $nt->http_code,
                           res          => $res, } );
};

# delete処理（application/json）
post '/delete' => sub {
  my $self = shift;

  # Postされた項目を取得
  my $csrftoken = $self->param('csrftoken');
  my $id = $self->param('id'); 

  # csrftokenをチェック
  if ( $csrftoken ne $self->session('csrftoken') ) {
    $self->render( json => { 'csrf' => '1',} );
    return;
  }
  $nt->destroy_status( $id );
  $self->render( json => { http_message => $nt->http_message, 
                           status       => $nt->http_code,
                           id           => $id,
                         } );
};

# Tweet処理（application/json）
post '/tweet' => sub {
  my $self = shift;

  # Postされた項目を取得
  my $csrftoken = $self->param('csrftoken');
  my $messageid = $self->param('messageid'); 
  my $to        = $self->param('to') || '';
  # Postされてきた送信先screen_name(to)を取得、正規化
  $to =~ s/\s.+//;

  # csrftokenをチェック
  if ( $csrftoken ne $self->session('csrftoken') ) {
    $self->render( json => { 'csrf' => '1',} );
    return;
  }

  # Twitter NGリストを読み込み
  my $nglist;
  {
    open my $fh, '<', app->home->rel_file('/public/ng.json');
    $nglist = decode_json( do { local $/; <$fh> } );
    close $fh;
    # NG ID検索のためスモールキャピタルに正規化
    map { $nglist->{lc($_)} = $nglist->{$_} } keys %$nglist;
  }
  # 送信先screen_name(to)がNGリストにあるかチェック
  ( my $to_lc = lc($to) ) =~ s/^@//;
  if ( exists $nglist->{$to_lc} ) {
    $self->render( json => { 'ng' => $to,} );
    return;
  }

  # キャラクターのメッセージを読み込み
  my $messages; 
  {
    open my $fh, '<', app->home->rel_file('/public/ayase.json');
    $messages = decode_json( do { local $/; <$fh> } );
    close $fh;
  }
  my $dic;
  foreach my $item ( @$messages ) {
    $dic->{$item->{id}} = $item->{text};
  }

  $to =~ s/^@//;
  $self->session->{screenname} = $to;
  my $arg;
  $arg->{status} = $dic->{$messageid};
  if ( $to ne '' ) { $arg->{status} = '@'."$to $arg->{status}"; }
  
  # post
  my $res = $nt->update( $arg );
  $self->render( json => { 'http_message' => $nt->http_message,} );
};

app->start;

__DATA__

@@ index.html.ep
% layout 'default',  title => '女子中学生にTwitterで罵ってもらえるサイト', description => 'あやせは450円のメインページ';
  
        <section class="hentry">
          <h2 class="entry-title">ラブリーマイエンジェルあやせたん（円／ドル相場Webアプリです）</h2>
          <p>
            <img id="buy" src="<%= url_for '/ayaseimg' %>"
              alt="character_image" style="width: auto; max-width: 100%;" />
          </p>

          <form class="fukidashi" id="message" name="message"
            method="post" action="<%= url_for '/tweet' %>" style="display: none;">
            <input type="hidden" name="messageid" value="" />
            <input type="hidden" name="csrftoken" value="<%= $csrftoken %>" />
            <p>
              <input type="text" name="to" value="@<%= $screenname %>" />
              <span id="comment"></span>
            </p>
            <p style="text-align: right; margin-top: 6px;">
            <input type="submit" name="submit" value="Tweetしてもらう" disabled="disabled" />
            </p>
          </form>

          <div class="fukidashi" id="response" style="display: none;">
          </div>

        </section>

        <section class="hentry howto">
          <h2 class="entry-title">あそびかた（Twitterで罵ってもらえるWebサイトです）</h2>
          <ol>
            <li>値段を確認します。</li>
            <li>画像をクリック（購入）します。※実際に購入はできません</li>
            <li>罵倒されます。</li>
            <li>罵倒された吹き出しの中の「Tweetしてもらう」をクリック</li>
            <li>「お兄さんは本当に変態ですね！」</li>
            <li>
            % my @a = qw(言葉の裏を読み取りましょう。 まずは警戒心を解きましょう。 
            % 残念！ 話題はもっと慎重に選びましょう。 アピールが足りないようです。がんばって！
            % よくできましたね。 人生には引き際も肝心です。 グッジョブ！
            % 惜しい！　必死さがにじみ出てしまいましたね。 大変よくできました。);
            <%= $a[int(rand($#a))]; %>
            </li>
          </ol>
        </section>

        %= javascript begin
        // Global Objects
        var ngList = {};

        // AJAX Setting
        // NGリストを読み込む
        $.getJSON('<%= url_for '/ng.json' %>', 
          {'_': new Date().getTime() }, 
          function(data){
          // Twitter Screen_nameでの検索用にスモールキャピタルに変換
          for ( var key in data ) {
            ngList[ key.toLowerCase() ] = data[ data[key] ];
          };
        });
        // 罵倒リストを読み込む
        $.getJSON('<%= url_for '/ayase.json' %>',
          {'_': new Date().getTime() },
          function(data){
          var batoList = data;
          $('#buy').click( function(){
            $('#response').hide('slow');
            var index = Math.floor( Math.random() * batoList.length );
            var bato = batoList[ index ]['text'];
            $('#comment').text( bato );
            $("input[name='messageid']").val( batoList[ index ]['id']);
            $('#message').slideDown("slow");
            $('ol>li').removeClass('cursor');
            $('ol>li').eq(3).addClass('cursor');
          });
        });
        
        // onload
        $(function() {
          
          // 送信先screenname正規化・チェック
          var chkTo = function() {
            var item = $('input[name="to"]');
            if ( item.val() == '') { item.val('@'); }
            if ( item.val().match(/^@\w+$/) ) {
              $('input[name="submit"]').removeAttr("disabled");
            } else {
              $('input[name="submit"]').attr("disabled","disabled");
            }
            // ngListからlookup
            if ( item.val().replace(/^@/,'').toLowerCase() in ngList ) {
              // $('input[name="submit"]').attr("disabled","disabled");
            }
          };
          // onloadのタイミングで一度チェック（セッションCookieより入力済みの場合がある）
          chkTo();
          
          // 使い方説明カーソル表示用
          $.each( $('ol>li'), function() {
            var html = $(this).html();
            $(this).html('<span>'+html+'</span>');
          });
          // onloadのタイミングで使い方説明カーソル移動
          $('ol>li').eq(1).addClass('cursor');

          /* イベント設定 */

          // 1. 送信先入力ボックスチェック
          $('input[name="to"]').keyup( chkTo ).keydown( chkTo );

          // 2. formの送信をしないように（JavaScriptでAJAXでPOSTする）
          $('#message').submit(function() { return false;});

          // 3. formのsubmitボタンにイベント設定
          $('input[name="submit"]').click( function() {
            // 使い方カーソルを次ステップに移動
            $('ol>li').removeClass('cursor');
            $('ol>li').eq(3).addClass('cursor');
            // submitボタンは無効化（AJAX送信中のインジケータ的意味も）
            $('input[name="submit"]').attr("disabled","disabled");
            // 返信吹き出しを隠す（AJAX通信後表示）
            $('#response').slideUp('slow');
            // AJAX通信で、ツイートをする。自由文でツイートできないように、
            // batoListのメッセージIDを指定する。
            $.ajax({
              type: "POST",
              url: "<%= url_for '/tweet' %>",
              data: "messageid=" + $('input[name="messageid"]').val()
                      +'&'+"to=" + $('input[name="to"]').val()
                      +'&'+"csrftoken=" + $('input[name="csrftoken"]').val(),
              success: function(data){
                // submitボタンを有効化する
                $('input[name="submit"]').removeAttr("disabled");
                // TwitterからのHTTPメッセージ
                var mes = data.http_message;
                // TwitterのHTTPメッセージだとわかりにくいので
                // キャラクターの発言に差し替えます。
                var str = mes;
                if ( mes == 'Forbidden' ) {
                  str = 'あれ？ お兄さん、もしかして'
                      + '同じ内容でツイート済みかもしれません。';
                } else if ( mes == 'Unauthorized' ) {
                  str = 'あれ？ お兄さん、Twitterのログイン認証に'
                      + 'はじかれているみたいです。'
                      + '時間をおいて試してみてください。'
                      + 'または、ツイート内容に使えない文字、'
                      + '半角の「! \' ( ) * [ ] 」が'
                      + '入っている可能性があります。Net::Twitter'
                      + 'の修正待ちですね。';
                } else if ( mes == 'Bad Gateway' ) {
                  str = 'あれ？ Twitterの調子が悪いみたいですね。'
                      + '書き込めているかもしれませんし、'
                      + '書き込めていないかもしれません。';
                } else if ( mes == 'Service Unavailable' ) {
                  str = 'あれ？ Twitterが止まっているみたいですね。';
                } else if ( mes == 'OK' ) {
                  $('ol>li').removeClass('cursor');
                  $('ol>li').eq(5).addClass('cursor');
                  str = '投稿済みです。お兄さんは本当に変態ですね！';
                }
                if ( 'ng' in data ) {
                  mes = 'NG';
                  str = data.ng + 'はシステム側で送信NGリストに入っているみたいです。';
                }
                if ( 'csrf' in data ) {
                  mes = 'csrf_error';
                  str = 'CSRF検出。Tweetを中止しました。';
                }
                $('#response').html('<p title="'+mes+'">'+str+'</p>').slideDown("slow");
              }
            });
          });
          
        });
        % end
    
    % content_for stylesheet => begin
    #buy {
      -webkit-transition: all 0.2s ease;
      transition: all 0.2s ease;
    }
    #buy.notouchdev:hover, #buy.hover {
      opacity: 0.5;
      cursor: pointer;
    }
    .fukidashi {
      margin-top: 12px;
      position: relative;
      border: 3px solid #f8a;
      text-align: left;
      border-radius: 8px;
      max-width: 360px;
      padding: 8px;
      background-color: white;
      opacity: 0.8;
      text-shadow: 1px 1px 3px #ddd;
    }
    .fukidashi:after, .fukidashi:before {
      content: "";
      position: absolute;
      top: 100%;
      height: 0;
      width: 0;
    }
    .fukidashi:after {
      left: 33px;
      top: -22px;
      border: 11px solid transparent;
      border-bottom: 11px solid #fff;
    }
    .fukidashi:before {
      left: 30px;
      top: -29px;
      border: 14px solid transparent;
      border-bottom: 14px solid #f8a;
    }
    .howto ol {
      padding-left: 2em;
      margin--left: 2em;

    }
    .howto ol li {
      list-style-type: decimal;
      margin--left: 2em;
      padding: 2px;
    }
    li.cursor {
      margin-top: 6px;
      margin-bottom: 6px;
    }
    li span {
      border: 2px solid transparent;
      border-radius: 4px;
      padding: 2px;
      color: #522;
      text-shadow: 1px 1px 3px #ddd;
      -webkit-transition: all 0.6s ease;
      transition: all 0.6s ease;
    }
    li.cursor span {
      border: 2px solid red;
    }
    % end

@@ edit.html.ep
% layout 'default', title => 'Edit - あやせ450円', description => 'あやせ450円の発言編集（削除）ページ';

        <section class="hentry">
          <h2 class="entry-title">Twitterでの発言</h2>
          <p>発言してはいけない人に向かって罵倒してしまったときのため、削除が出来ます。発言を選んで、削除ボタンを押してください。</p>
          <label for="none" id="notselected" style="z-index: 0;">
          </label>
          <form id="delform" method="post" action="<%= url_for '/delete' %>">
            <input type="hidden" name="csrftoken" value="<%= $csrftoken %>" />
            <input type="radio" name="id" value="0" id="none" style="display: none;" />
            <ul id="tweetlist">
              Tweetの削除は、JavaScriptが使えるブラウザでお願いします。
            </ul>
          </form>
        </section>

        %= javascript begin
        // Twitter発言リストをJSONで取得
        $.getJSON('<%= url_for '/list' %>',
          {'_': new Date().getTime() },
          function(data) {
          $('#tweetlist').css({ border: '1px solid #ddd', 'border-bottom': '0px'});
          var res = data.res;
          $(res).each( function() {
            var f = this;
            if (typeof f.in_reply_to_screen_name != 'undefined') {
              var rep = f.in_reply_to_screen_name;
              var re = new RegExp('@('+rep+')', 'gi');
              f.text = f.text.replace( re, '<a target="_blank" '
               + 'href="https://twitter.com/' + "$1" + '/">@' + "$1" + '</a>');
            }
            var elm = $('<li>').html(''
              + '<label for="r_' + f.id_str +'" onclick="">'
              + '  <a target="_blank" href="https://twitter.com/' + f.user.screen_name + '">'
              + '    <img class="profileimage" src="'
              + f.user.profile_image_url_https
              + '" width="48" height="48" />'
              + '  </a>'
              + '  <div class="content">'
              + '    <p class="showname">'
              + '      <a target="_blank" href="https://twitter.com/' + f.user.screen_name + '">'
              + '        <span class="username">' + f.user.name + '</span>'
              + '        <span class="screenname">@'+ f.user.screen_name +'</span>'
              + '      </a>'
              + '    </p>'
              + '    <p><span class="text">' + f.text + '</span></p>'
              + '    <p class="datetime"><a target="_blank" href="https://twitter.com/'
              + f.user.screen_name+'/status/'+ f.id_str +'"><time>'
              + f.created_at + '</time></a></p>'
              + '    <input class="radiobutton" name="id" type="radio" value="'
              + f.id_str + '" id="r_' + f.id_str + '" />'
              + '    <input type="submit" name="submit" value="削除" />'
              + '  </div>'
              + '</label>'
            );
            if ( typeof document.ontouchstart == "undefined" ) {
              // 新しく作ったli要素に、タッチデバイス以外用クラス設定（hoverで色が変わる）
              elm.addClass('notouchdev');
            } else {
              // 新しく作ったli要素に、タッチデバイス用イベント設定（タッチ中色が変わる）
              elm.bind( 'touchstart', function(){ $( this ).addClass( 'hover' ) });
              elm.bind( 'touchend'  , function(){ $( this ).delay(400).removeClass( 'hover' ); });
            }
            // 新しく作ったli要素に、指定用IDを付ける（削除するとき指定する）
            elm.attr('id', 'rr_' + f.id_str);
            // 新しく作ったli要素を、ol要素に追加する
            elm.appendTo('#tweetlist');
          });
        });

        // onload
        $(function() {
          // 1. tweetlistの中身を空にする（non-javascriptブラウザ用）
          $('#tweetlist').empty();

          // 2. formの送信をしないように（JavaScriptでAJAXでPOSTする）
          $('#delform').submit(function() { return false;});

          // 3. formのsubmitボタンにイベント設定
          $(document).on('click', 'input[name="submit"]', function() {
            $.ajax({
              type: "POST",
              url: "<%= url_for '/delete' %>",
              data: "id=" + $('input[name="id"]:checked').val()
                      +'&'+"csrftoken=" + $('input[name="csrftoken"]').val(),
              success: function(data){
                alert( data.http_message );
                if ( data.http_message == 'OK' ) {
                  $('#rr_' + data.id).slideUp('slow' ,function(){$(this).remove});
                }
              }
            });
          });
          // 4. 隠しラジオボタンチェック済みの時に外側のボックスにクラス付加（色替え）
          $(document).on('change','input[type=radio]', function() {
            $('li').removeClass('checked');
            $('#r'+$(this).attr('id') ).addClass('checked');
          });
          // 5. IEの時、隠しラジオボタンが動作しないので、やむを得ず表示
          if (navigator.userAgent.indexOf('MSIE') == -1) {
            $('#tweetlist').addClass('noie');
          } 
        });
        % end
        
    % content_for stylesheet => begin
    #notselected {
      display: block;
      height: 100%;
      left: 0;
      position: absolute;
      top: 0;
      width: 100%;
    }
    #tweetlist {
      background-color: white;
      border-bottom: 0px;
    }
    #tweetlist li {
      border-bottom: 1px solid #ddd;
      margin: 0px 0px;
      position: relative;
      -webkit-transition: all 0.2s ease;
      transition: all 0.2s ease;
    }
    #tweetlist li.notouchdev:hover, #tweetlist li.hover {
      background-color: #f3f3f3;
    }
    #tweetlist li.checked{
      background-color: #fdb;
    }
    #tweetlist li.checked.notouchdev:hover, #tweetlist li.hover {
      background-color: #fcc;
    }
    #tweetlist label {
      display: block;
    }
    #tweetlist.noie input.radiobutton {
      display: none;
    }
    #tweetlist p {
      line-height: 1.4;
      margin-top: 0px;
      margin-bottom: 0px;
    }
    #tweetlist .showname {
      margin-top: 0px;
      padding-top: 8px;
    }
    #tweetlist .username {
      font-weight: bold;
      color: #222;
    }
    #tweetlist .screenname {
      font-size: 85%;
      color: #aaa;
    }
    #tweetlist img {
      position: absolute;
      top: 12px;
      left: 12px;
    }
    #tweetlist li .content {
      padding-left: 72px;
      padding-right: 8px;
    }
    #tweetlist .datetime {
      padding-bottom: 8px;
    }
    #tweetlist time {
      font-size: 85%;
      color: #aaa;
    }
    #tweetlist input[type=submit] {
      display: none;
      -webkit-transition: all 0.2s ease;
      transition: all 0.2s ease;
      position: absolute;
      top: 8%;
      right: 1%;
    }
    #tweetlist .checked input[type=submit] {
      display: inline;
    }
    %= end

@@ development.html.ep
% layout 'default', title => 'Development - あやせ450円', description => 'あやせ450円の開発ページ';

        <section class="hentry">
          <h2 class="entry-title">GitHub</h2>
          <p><a href="https://github.com/CLCL/ayase" target="_blank">https://github.com/CLCL/ayase</a></p>
        </section>
        <section class="hentry">
          <h2 class="entry-title">元ネタ</h2>
          <p>
            俺の妹がこんなに可愛いわけがないiP<br />
            http://www.bandainamcogames.co.jp/mobile/app.php?id=807
          </p>
          <p>
            <img src="<%= url_for '/images/ayase-original.jpg' %>"
              alt="original_image" style="width: auto; max-width: 100%;" />
          </p>
        </section>

@@ layouts/default.html.ep
<!DOCTYPE html> 
<html lang="ja">

  <head>
    <%= include 'head_common.inc' =%>
  </head>

  <body class="<%= current_route %>">
    <div id="doc">
      <header id="hd"><!-- header -->
        <%= include 'header.inc' %>
      </header>   
      <div id="bd" class="hfeed"><!-- body -->
        <%= content %>
      </div> 
      <footer>
      </footer>
    </div>
    <script type="text/javascript">
    <%= include 'common.js' %>
    </script>
  </body>
</html>

@@ head_common.inc.html.ep
    <meta charset="UTF-8" />
    <title><%= $title %></title>
    <meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1" />
    <meta name="viewport" content="width=device-width, user-scalable=yes" />
    <meta name="description" content="<%= $description %>" />
    <meta property="og:title" content="<%= title %>" />
    <meta property="og:url" content="<%= url_for('current')->to_abs %>" />
    <meta property="og:type" content="website" />
    <meta property="og:email" content="ayase@mamesibori.net" />
    <meta property="og:image" content="<%= url_for('/images/ayase_base.png')->to_abs %>" />
    <meta property="og:locale" content="ja_JP" />
    <meta property="og:site_name" content="<%= $title %>" />
    <meta property="og:description" content="<%= $description %>" />
    <%= include 'styles.css' =%>
    %= stylesheet begin
    <%= content_for 'stylesheet' =%>
    %= end
    %= javascript '/js/jquery.js'
    <!--[if lt IE 9]>
    %= javascript 'http://ie7-js.googlecode.com/svn/version/2.1(beta4)/IE9.js'
    %= javascript '/js/html5shiv.js'
    <![endif]-->

@@ header.inc.html.ep
        <h1>
          <a href="./">
            あやせは450円
          </a>
        </h1>
        <nav style="position: relative;">
          <ul id="menu" style="z-index: 10; position: relative;">
            <li class="index"      ><%= link_to index       => begin %>Home<% end %></li>
            <li class="edit"       ><%= link_to edit        => begin %>Edit<% end %></li>
            <li class="development"><%= link_to development => begin %>Development<% end %></li>
          </ul>
        </nav>

@@ common.js.html.ep
        // common.js.html.ep 各ページ共通に使うJavaScript
        /* onload */
        $( function() {

          // touchデバイスじゃないなら、hoverするアイテムにnotouchdevクラス付ける
          if ( typeof document.ontouchstart == "undefined" ) {
            $('a').addClass('notouchdev');
            $('#buy').addClass('notouchdev');
          }

          // touchデバイス用にイベント付ける（タッチ中に色を変える）
          $( 'a, input[type="button"], input[type="submit"], button, #buy')
            .bind( 'touchstart', function(){
              $( this ).addClass( 'hover' );
          }).bind( 'touchend', function(){
              $( this ).delay(400).removeClass( 'hover' );
          });   

          // スマートフォン用アドレスバー隠し
          var hideBar = function () {
            setTimeout("scrollTo(0,1)", 100);
          }
          $(window).bind("orientationchange",function(){
            if(Math.abs(window.orientation) === 90){
              hideBar();
            }else{
              hideBar();
            }
          });
          hideBar(); // onloadのタイミングで一度アドレスバー隠し

        });   
          
@@ styles.css.html.ep
    %# Yahoo UI Font Size
    %# ----------------
    %# |  px  |   %   |
    %# |--------------|
    %# |  10  |  77   |
    %# |  11  |  85   |
    %# |  12  |  93   |
    %# |  13  | 100   |
    %# |  14  | 108   |
    %# |  15  | 116   |
    %# |  16  | 123.1 |
    %# |  17  | 131   |
    %# |  18  | 138.5 |
    %# |  19  | 146.5 |
    %# |  20  | 153.9 |
    %# |  21  | 161.6 |
    %# |  22  | 167   |
    %# |  23  | 174   |
    %# |  24  | 182   |
    %# |  25  | 189   |
    %# |  26  | 197   |
    %# ----------------
    %#
    %= stylesheet 'http://yui.yahooapis.com/3.8.1/build/cssreset/cssreset-min.css'
    %= stylesheet 'http://yui.yahooapis.com/3.8.1/build/cssfonts/cssfonts-min.css'
    %= stylesheet begin
    /* styles.css.html.ep 共通CSS */
    html {
      background-image: url(<%= url_for '/images/bg.jpg' %>);
    }
    body {
      padding: 10px;
      font-family: 'メイリオ', Meiryo, 'ＭＳ Pゴシック', Sans
    }
    h1, p {
      text-shadow: 1px 1px 3px #ddd;
    }
    header p {
      text-align: left;
    }
    header h1 {
      text-align: left;
      font-size: 108%;
    }
    header h1 a, header h1 a:hover {
      color: #999;
          -webkit-text-shadow: none;
          -moz-text-shadow: none;
          text-shadow: none;
          cursor: default;
    }
    section h1 {
      text-align: left;
    }
    section p {
      text-align: left;
    }
    a {
      color: #26c;
      -webkit-transition: all 0.2s ease;
      transition: all 0.2s ease;
      text-decoration: none;
    }
    a.notouchdev:hover {
      color: #129;
      -webkit-text-shadow: 0px 0px 8px #89b3dd;
      -moz-text-shadow: 0px 0px 8px #89b3dd;
      text-shadow: 0px 0px 5px #89b3dd;
    }
    a:active {
      color: #666;
    }
    #doc {
      width: 100%;
    }
    #bd h2 {
      background-color: #ffc1c1;
      font-size: 138.5%;
      margin: 16px 0px;
      padding: 16px;
      color: #93252a;
      font-weight: bold;
      border-radius: 4px;
      text-shadow: 0 0 0 transparent, 1px 1px 0 #fff;
      behavior: url(<%= url_for '/PIE.htc' %>);
      position: relative;
    }
    #bd p {
      line-height: 180%;
      margin: 4px 0px;
      color: #522;
      text-shadow: 1px 1px 3px #ddd;
    }
    #menu {
      text-align: right;
    }
    #menu:after {  
      content: ".";   
      display: block;   
      height: 0;   
      clear: both;   
      visibility: hidden;  
    }  
    #menu li {
      margin-left: 5px;
      padding-left: 5px;
      border-left: 1px dotted #bbb;
      display: inline-block;
    }
    #menu li:first-child {
      border-left: 0px;
      padding-left: 0px;
    }
    body.index .index a {
      text-decoration: underline;
      color: #999;
    }
    body.edit .edit a {
      text-decoration: underline;
      color: #999;
    }
    body.development .development a {
      text-decoration: underline;
      color: #999;
    }
    %= end
