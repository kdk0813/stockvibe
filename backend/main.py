import logging
import sys
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String
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
def get_stock_history(symbol: str):
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="7d")
        if data.empty:
            return []
        return [{"date": str(d.date()), "price": round(p, 2)} for d, p in zip(data.index, data['Close'])]
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
            data = ticker.history(period="2d")
            if not data.empty:
                cp = data['Close'].iloc[-1]
                pc = data['Close'].iloc[-2] if len(data) > 1 else cp
                ch = cp - pc
                pct = (ch / pc) * 100 if pc != 0 else 0
                results.append({"symbol": item.symbol, "price": round(cp, 2), "change": round(ch, 2), "changesPercentage": round(pct, 2)})
            else:
                results.append({"symbol": item.symbol, "price": 0, "change": 0, "changesPercentage": 0})
        except Exception:
            results.append({"symbol": item.symbol, "price": 0, "change": 0, "changesPercentage": 0})
    return results

@app.post("/watchlist/{symbol}")
def add_to_watchlist(symbol: str, db: Session = Depends(get_db)):
    db_item = db.query(Watchlist).filter(Watchlist.symbol == symbol.upper()).first()
    if not db_item:
        new_item = Watchlist(symbol=symbol.upper())
        db.add(new_item)
        db.commit()
    return {"message": "Success"}

@app.delete("/watchlist/{symbol}")
def remove_from_watchlist(symbol: str, db: Session = Depends(get_db)):
    db_item = db.query(Watchlist).filter(Watchlist.symbol == symbol.upper()).first()
    if db_item:
        db.delete(db_item)
        db.commit()
    return {"message": "Success"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
