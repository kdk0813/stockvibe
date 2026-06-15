import logging
import sys
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import yfinance as yf
import uvicorn

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- 데이터베이스 설정 ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./stockvibe.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Watchlist(Base):
    __tablename__ = "watchlist"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, index=True)
    purchase_price = Column(Float, default=0.0) # 매수 단가
    quantity = Column(Integer, default=0)       # 보유 수량

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- FastAPI 앱 설정 ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to StockVibe API"}

@app.get("/stock/{symbol}")
def get_stock_price(symbol: str):
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="2d")
        if data.empty:
            raise HTTPException(status_code=404, detail="Stock not found")
        current_price = data['Close'].iloc[-1]
        prev_close = data['Close'].iloc[-2] if len(data) > 1 else current_price
        change = current_price - prev_close
        pct_change = (change / prev_close) * 100 if prev_close != 0 else 0
        return {
            "symbol": symbol.upper(),
            "price": round(current_price, 2),
            "change": round(change, 2),
            "changesPercentage": round(pct_change, 2)
        }
    except Exception as e:
        logger.error(f"Price Error {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stock/{symbol}/history")
def get_stock_history(symbol: str, period: str = "7d"):
    try:
        ticker = yf.Ticker(symbol)
        # period에 따라 interval 조정 (1일치면 분 단위, 그 외에는 일 단위)
        interval = "1m" if period == "1d" else "1d"
        data = ticker.history(period=period, interval=interval)
        
        if data.empty:
            return []
        
        results = []
        for d, p in zip(data.index, data['Close']):
            # 1일 데이터는 시간을 포함, 그 외는 날짜만 표시
            date_str = d.strftime("%H:%M") if period == "1d" else str(d.date())
            results.append({"date": date_str, "price": round(p, 2)})
        return results
    except Exception as e:
        logger.error(f"History Error {symbol}: {str(e)}")
        return []

@app.get("/stock/{symbol}/news")
def get_stock_news(symbol: str):
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        return [{"title": n.get("title"), "publisher": n.get("publisher"), "link": n.get("link"), "publishTime": n.get("providerPublishTime")} for n in news[:5]]
    except Exception as e:
        logger.error(f"News Error {symbol}: {str(e)}")
        return []

@app.get("/stock/{symbol}/info")
def get_stock_info(symbol: str):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return {
            "longName": info.get("longName", symbol.upper()),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "marketCap": info.get("marketCap", 0),
            "trailingPE": info.get("trailingPE", 0),
            "dividendYield": info.get("dividendYield", 0),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh", 0),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow", 0),
            "longBusinessSummary": info.get("longBusinessSummary", "상세 정보가 없습니다.")
        }
    except Exception as e:
        logger.error(f"Info Error {symbol}: {str(e)}")
        return {"longName": symbol.upper(), "longBusinessSummary": "정보를 불러올 수 없습니다."}

@app.get("/search/{query}")
def search_stock(query: str):
    results = []
    # 1. 사용자가 입력한 값을 즉시 추가할 수 있는 옵션 제공
    results.append({"symbol": query.upper(), "name": f"직접 입력: {query}", "exchange": "Manual"})
    
    # 2. yfinance 검색 시도 (실패해도 1번은 유지)
    try:
        search = yf.Search(query, max_results=5)
        if hasattr(search, 'quotes'):
            for quote in search.quotes:
                s = quote.get("symbol")
                n = quote.get("longname") or quote.get("shortname")
                if s and n:
                    results.append({"symbol": s, "name": n, "exchange": quote.get("exchange")})
    except Exception as e:
        logger.warning(f"Search API failed: {str(e)}")
    
    return results

@app.get("/watchlist")
def get_watchlist(db: Session = Depends(get_db)):
    items = db.query(Watchlist).all()
    results = []
    for item in items:
        try:
            ticker = yf.Ticker(item.symbol)
            data = ticker.history(period="1d")
            if not data.empty:
                cp = data['Close'].iloc[-1]
                pc = data['Open'].iloc[-1] # 당일 시가 기준 변동 계산
                ch = cp - pc
                pct = (ch / pc) * 100 if pc != 0 else 0
                
                # 포트폴리오 계산
                total_cost = item.purchase_price * item.quantity
                total_value = cp * item.quantity
                profit = total_value - total_cost if item.quantity > 0 else 0
                return_pct = (profit / total_cost * 100) if total_cost > 0 else 0
                
                results.append({
                    "symbol": item.symbol, 
                    "price": round(cp, 2), 
                    "change": round(ch, 2), 
                    "changesPercentage": round(pct, 2),
                    "purchase_price": item.purchase_price,
                    "quantity": item.quantity,
                    "profit": round(profit, 2),
                    "returnPercentage": round(return_pct, 2)
                })
            else:
                results.append({"symbol": item.symbol, "price": 0, "change": 0, "changesPercentage": 0, "purchase_price": item.purchase_price, "quantity": item.quantity, "profit": 0, "returnPercentage": 0})
        except Exception:
            results.append({"symbol": item.symbol, "price": 0, "change": 0, "changesPercentage": 0, "purchase_price": item.purchase_price, "quantity": item.quantity, "profit": 0, "returnPercentage": 0})
    return results

@app.post("/watchlist/{symbol}")
def add_to_watchlist(symbol: str, db: Session = Depends(get_db)):
    db_item = db.query(Watchlist).filter(Watchlist.symbol == symbol.upper()).first()
    if not db_item:
        new_item = Watchlist(symbol=symbol.upper())
        db.add(new_item)
        db.commit()
    return {"message": "Success"}

@app.post("/portfolio/{symbol}")
def update_portfolio(symbol: str, purchase_price: float, quantity: int, db: Session = Depends(get_db)):
    db_item = db.query(Watchlist).filter(Watchlist.symbol == symbol.upper()).first()
    if db_item:
        db_item.purchase_price = purchase_price
        db_item.quantity = quantity
        db.commit()
        return {"message": "Success"}
    raise HTTPException(status_code=404, detail="Stock not in watchlist")

@app.delete("/watchlist/{symbol}")
def remove_from_watchlist(symbol: str, db: Session = Depends(get_db)):
    db_item = db.query(Watchlist).filter(Watchlist.symbol == symbol.upper()).first()
    if db_item:
        db.delete(db_item)
        db.commit()
    return {"message": "Success"}

@app.get("/market-movers")
def get_market_movers():
    try:
        # 주요 감시 종목군 (KOSPI/NASDAQ 주요 종목 혼합)
        major_tickers = [
            "005930.KS", "000660.KS", "035420.KS", "035720.KS", "005380.KS", # 삼성, 하이닉스, 네이버, 카카오, 현대차
            "AAPL", "TSLA", "NVDA", "MSFT", "GOOGL", "AMZN", "AMD" # 애플, 테슬라, 엔비디아 등
        ]
        
        results = []
        for symbol in major_tickers:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="2d")
            if not data.empty:
                cp = data['Close'].iloc[-1]
                pc = data['Close'].iloc[-2] if len(data) > 1 else cp
                ch = cp - pc
                pct = (ch / pc) * 100 if pc != 0 else 0
                
                # 이름 가져오기 (캐싱 고려 안 함)
                name = symbol.split('.')[0]
                results.append({
                    "symbol": symbol,
                    "name": name,
                    "price": round(cp, 2),
                    "change": round(ch, 2),
                    "changesPercentage": round(pct, 2)
                })
        
        # 등락률 순으로 정렬
        sorted_results = sorted(results, key=lambda x: x['changesPercentage'], reverse=True)
        return {
            "gainers": sorted_results[:5],
            "losers": sorted_results[-5:][::-1]
        }
    except Exception as e:
        logger.error(f"Market Movers Error: {str(e)}")
        return {"gainers": [], "losers": []}

@app.get("/market-indices")
def get_market_indices():
    indices = {
        "^KS11": "코스피",
        "^KQ11": "코스닥",
        "^GSPC": "S&P 500",
        "^IXIC": "나스닥",
        "USDKRW=X": "원/달러 환율",
        "GC=F": "금 (선물)",
        "BTC-USD": "비트코인"
    }
    results = []
    for symbol, name in indices.items():
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="2d")
            if not data.empty:
                cp = data['Close'].iloc[-1]
                pc = data['Close'].iloc[-2] if len(data) > 1 else cp
                ch = cp - pc
                pct = (ch / pc) * 100 if pc != 0 else 0
                results.append({
                    "symbol": symbol,
                    "name": name,
                    "price": round(cp, 2),
                    "change": round(ch, 2),
                    "changesPercentage": round(pct, 2)
                })
        except Exception as e:
            logger.error(f"Index Error {symbol}: {str(e)}")
    return results

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
