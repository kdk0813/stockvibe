from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf

app = FastAPI()

# 프론트엔드와의 통신을 위한 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 도메인 허용 (개발용)
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
        data = ticker.history(period="1d")
        if data.empty:
            return {"error": "Stock symbol not found"}
        
        current_price = data['Close'].iloc[-1]
        return {
            "symbol": symbol.upper(),
            "price": round(current_price, 2)
        }
    except Exception as e:
        return {"error": str(e)}
