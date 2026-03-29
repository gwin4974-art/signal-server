from flask import Flask, jsonify
from flask_cors import CORS
import requests, statistics, math

app = Flask(__name__)
CORS(app)

ASSET_MAP = {
    "EUR/USD":{"type":"forex","from":"EUR","to":"USD"},
    "GBP/USD":{"type":"forex","from":"GBP","to":"USD"},
    "USD/JPY":{"type":"forex","from":"USD","to":"JPY"},
    "AUD/USD":{"type":"forex","from":"AUD","to":"USD"},
    "USD/CAD":{"type":"forex","from":"USD","to":"CAD"},
    "EUR/GBP":{"type":"forex","from":"EUR","to":"GBP"},
    "BTC/USD":{"type":"crypto","id":"bitcoin"},
    "ETH/USD":{"type":"crypto","id":"ethereum"},
}

FALLBACK = {
    "EUR/USD":1.08452,"GBP/USD":1.27134,"USD/JPY":149.832,
    "AUD/USD":0.65321,"USD/CAD":1.36540,"EUR/GBP":0.85312,
    "BTC/USD":67450.0,"ETH/USD":3521.0,
}

price_history = {a:[] for a in ASSET_MAP}

def fetch_forex(f,t):
    try:
        r=requests.get(f"https://api.frankfurter.app/latest?from={f}&to={t}",timeout=8)
        d=r.json()
        if d and "rates" in d and t in d["rates"]: return d["rates"][t]
    except: pass
    return None

def fetch_crypto(id):
    try:
        r=requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={id}&vs_currencies=usd",timeout=8)
        d=r.json()
        if d and id in d: return d[id]["usd"]
    except: pass
    return None

def ema(prices,p):
    if len(prices)<p: return prices[-1] if prices else 0
    k=2/(p+1); e=sum(prices[:p])/p
    for x in prices[p:]: e=x*k+e*(1-k)
    return e

def rsi(prices,p=14):
    if len(prices)<p+1: return 50.0
    g=l=0
    for i in range(len(prices)-p,len(prices)):
        d=prices[i]-prices[i-1]
        if d>0: g+=d
        else: l+=abs(d)
    if l==0: return 100.0
    return 100-(100/(1+g/l))

def bollinger(prices,p=20):
    sl=prices[-p:] if len(prices)>=p else prices
    m=sum(sl)/len(sl)
    std=math.sqrt(sum((x-m)**2 for x in sl)/len(sl))
    return m+2*std,m,m-2*std

def stochastic(prices,p=14):
    sl=prices[-p:] if len(prices)>=p else prices
    hi,lo=max(sl),min(sl)
    if hi==lo: return 50.0
    return ((prices[-1]-lo)/(hi-lo))*100

def analyze(prices,cur):
    score=0; sigs={}
    e9=ema(prices,9); e21=ema(prices,21)
    r=rsi(prices); mc=ema(prices,12)-ema(prices,26)
    bu,bm,bl=bollinger(prices); st=stochastic(prices)
    if e9>e21: score+=1; sigs["ema"]={"cls":"bull","txt":"Bullish Cross","val":f"{e9:.5f}"}
    else: score-=1; sigs["ema"]={"cls":"bear","txt":"Bearish Cross","val":f"{e9:.5f}"}
    if r<35: score+=1; sigs["rsi"]={"cls":"bull","txt":"Oversold","val":f"{r:.1f}"}
    elif r>65: score-=1; sigs["rsi"]={"cls":"bear","txt":"Overbought","val":f"{r:.1f}"}
    else: sigs["rsi"]={"cls":"neut","txt":"Neutral","val":f"{r:.1f}"}
    if mc>0: score+=1; sigs["macd"]={"cls":"bull","txt":"Bullish","val":f"{mc:.5f}"}
    else: score-=1; sigs["macd"]={"cls":"bear","txt":"Bearish","val":f"{mc:.5f}"}
    if cur<=bl*1.001: score+=1; sigs["bb"]={"cls":"bull","txt":"Lower Band","val":f"L:{bl:.5f}"}
    elif cur>=bu*0.999: score-=1; sigs["bb"]={"cls":"bear","txt":"Upper Band","val":f"U:{bu:.5f}"}
    else: sigs["bb"]={"cls":"neut","txt":"Mid Range","val":f"M:{bm:.5f}"}
    if st<25: score+=1; sigs["stoch"]={"cls":"bull","txt":"Oversold","val":f"{st:.1f}"}
    elif st>75: score-=1; sigs["stoch"]={"cls":"bear","txt":"Overbought","val":f"{st:.1f}"}
    else: sigs["stoch"]={"cls":"neut","txt":"Neutral","val":f"{st:.1f}"}
    ab=abs(score)
    return {"isUp":score>0,"score":score,"confidence":"HIGH" if ab>=4 else "MEDIUM" if ab>=3 else "LOW","signals":sigs,"candles":len(prices),"dataQuality":"real" if len(prices)>=20 else "partial"}

@app.route("/")
def home(): return jsonify({"status":"PocketSignal server running"})

@app.route("/ping")
def ping(): return jsonify({"status":"ok"})

@app.route("/signal/<path:asset>")
def get_signal(asset):
    asset=asset.upper().replace("-","/")
    cfg=ASSET_MAP.get(asset)
    if not cfg: return jsonify({"error":"Unknown asset"}),404
    price=fetch_forex(cfg["from"],cfg["to"]) if cfg["type"]=="forex" else fetch_crypto(cfg["id"])
    live=bool(price)
    if not live: price=FALLBACK.get(asset,1.0)
    price_history[asset].append(price)
    if len(price_history[asset])>200: price_history[asset].pop(0)
    prices=price_history[asset]
    if len(prices)>=10:
        result=analyze(prices,price)
    else:
        import random; up=random.random()>0.45
        result={"isUp":up,"score":2 if up else -2,"confidence":"LOW","signals":{"ema":{"cls":"bull" if up else "bear","txt":"Uptrend" if up else "Downtrend","val":""},"rsi":{"cls":"bull" if up else "bear","txt":"Oversold" if up else "Overbought","val":"34" if up else "68"},"macd":{"cls":"bull" if up else "bear","txt":"Bullish" if up else "Bearish","val":""},"bb":{"cls":"bull" if up else "bear","txt":"Lower Band" if up else "Upper Band","val":""},"stoch":{"cls":"bull" if up else "bear","txt":"Oversold" if up else "Overbought","val":"18" if up else "82"}},"candles":len(prices),"dataQuality":"sim"}
    result["price"]=price; result["asset"]=asset; result["live"]=live
    return jsonify(result)

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)
