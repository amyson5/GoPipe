# GoPipe
A pipe connecting gtp controller and engines

## 远程引擎
远程是ikatago server, 用别的也可以，用`ssh`连接（使用`paramiko`库）， `ip`等参数在`config.ini`中的 [ENGINE] 中设置。

## 本地引擎
默认是在`$HOME`目录下建立`.gopipe`，在里面的`katago`目录中放置可执行文件，权重以及配置文件。
相应的设置在`config.ini`中的`[LOCAL]` section.

## 使用 ikatago client
也可以直接使用`ikatago client`. 默认是把`ikatago.exe`放在`~\.gopipe`.
相应的设置在`config.ini`中的`[IKATAGO]` section.

## log files
日志文件存在`~\.gopipe\log`. 实时赢率在相应文件中查看……