# Minimal Multiplayer Game Experiment (Python)

## 1. 我想做的事情 (Goal)

我想自己 **親手驗證多人遊戲的 server / client 架構**，並理解以下事情：

* 多人遊戲實際上如何同步玩家資料
* server 與 client 的責任如何分離
* host player（自己開房間）是怎麼運作的
* 是否一定要分成兩個程式
* 實際代碼大概長什麼樣子

我不希望一開始就使用像 **Unity 或 Unreal** 這種 heavy engine。

我希望：

* 用 **最小的 Python 專案**
* 可以在 **本地測試 multiplayer**
* 可以 **同時開兩個 client**
* 透過 server 同步狀態

我本地有 Docker，但不一定要用 Docker。

---

# 2. 我希望做到的實驗

我希望可以做一個非常簡單的 demo：

例如：

* server 管理玩家座標
* client 傳送移動指令
* server 廣播所有玩家的位置
* client 顯示目前 world state

測試方式：

```
terminal 1 → server
terminal 2 → client A
terminal 3 → client B
```

當 client A 移動時
client B 會看到同步。

---

# 3. 我目前想驗證的問題

## 問題 1

像 Minecraft 這種遊戲：

是不是 **真的有 server 與 client 兩個程式**？

例如：

```
minecraft_server
minecraft_client
```

client 負責：

* 顯示畫面
* 送 input

server 負責：

* world state
* physics
* multiplayer sync

---

## 問題 2

很多遊戲都有

```
Start Server
Host Game
```

但 **host player 也能玩**

那是不是代表：

```
同一台電腦

server + client
```

例如：

```
Host PC

server
client (host player)

Other PCs

client
client
```

我想知道這個架構 **實際上怎麼寫的**。

---

## 問題 3

多人遊戲一定要：

```
server build
client build
```

兩份程式嗎？

還是其實可以：

```
game.exe --server
game.exe --client
```

同一個 binary。

---

## 問題 4

我想看看 **最小多人遊戲代碼長什麼樣子**。

最好：

* 100 行左右
* server / client
* 可以本地跑
* 能同步玩家位置

---

# 4. 我希望的專案形式

請幫我生成一個 **最小 multiplayer Python 專案**。

建議：

```
mini_multiplayer_game/

server.py
client.py
```

使用：

```
websocket
asyncio
```

功能：

server：

* 接收 client 連線
* 保存 players
* 接收 move 指令
* 廣播 world state

client：

* 連線 server
* 用 WASD 移動
* 接收 world state
* print world state

---

# 5. 測試方式

開三個 terminal：

```
python server.py
python client.py
python client.py
```

client 輸入：

```
w
a
s
d
```

server 更新位置並同步。

---

# 6. 如果可以，希望再升級

如果 demo 成功，希望能再升級為：

### v2 demo

加入：

* pygame 視窗
* 玩家方塊
* 移動同步
* server authoritative
* tick rate

但 **先完成 v1 即可**。

---

# 7. 生成要求

請生成：

1. **完整可執行專案**
2. 提供

   * server.py
   * client.py
3. 提供

   * requirements.txt
4. 提供

   * README.md

README 需要包含：

* 安裝
* 執行
* 測試方式

整個專案希望保持 **簡單、清晰、可讀性高**。
