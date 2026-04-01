import time, threading, warnings
from typing import Dict, Optional
import pandas as pd
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.common import BarData
warnings.filterwarnings("ignore")

def donchian_channel(df: pd.DataFrame, period: int = 30) -> pd.DataFrame:
    # Calc upper band (highest high over the period)
    df["upper"] = df["high"].rolling(window=period).max()

    # Calc lower band (lowest low over the period)
    df["lower"] = df["low"].rolling(window=period).min()

    # Calc the middle line
    df["middle"] = (df["upper"] + df["lower"]) / 2

    return df

class TradingApp(EClient, EWrapper):
    def __init__(self):
        EClient.__init__(self, self)
        self.data: Dict[int, pd.DataFrame] = {}
        self.nextOrderId: Optional[int] = None

    def error(
            self, reqId: int, errorTime: int, errorCode: int, errorString: str, advancedOrderReject: str
    ) -> None:
        print(f"Status:")
        print(
            f"reqId: {reqId}, errorCode: {errorCode}, errorString: {errorString}"
        )

    def nextValidId(self, orderId: int) -> None:
        super().nextValidId(orderId)
        self.nextOrderId = orderId

    def get_historical_data(self, reqId: int, contract: Contract) -> pd.DataFrame:
        self.data[reqId] = pd.DataFrame(columns=[
            "time", "high", "low", "close"
        ])
        self.data[reqId].set_index("time", inplace=True)
        self.reqHistoricalData(
            reqId=reqId,
            contract=contract,
            endDateTime="",
            durationStr="1 D",
            barSizeSetting="1 min",
            whatToShow="MIDPOINT",
            useRTH=0,
            formatDate=2,
            keepUpToDate=False,
            chartOptions=[],
        )
        time.sleep(5)
        
        return self.data[reqId]
    
    def historicalData(self, reqId: int, bar: BarData) -> None:
        # Get the current DataFrame at the request ID
        df = self.data[reqId]

        # Set the current bar data into the DF
        df.loc[
            bar.date,
            ["high", "low", "close"]
        ] = [
            bar.high, bar.low, bar.close
        ]

        # Cast data to floats
        df = df.astype(float)

        # Assign the DF at the request ID
        self.data[reqId] = df

    @staticmethod
    def get_contract(symbol: str) -> Contract:
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"

        return contract
    
    def place_order(
            self, contract: Contract, action: str, order_type: str, quantity: int
    ) -> None:
        order = Order()
        order.action = action
        order.orderType = order_type
        order.totalQuantity = quantity

        self.placeOrder(self.nextOrderId, contract, order)
        self.nextOrderId += 1
        print(f"Buy order placed")


# Create instance of trading app, can connect up to 32 different apps == 32 different stratagies
app = TradingApp()

# Connect
localhost, port, clientId = "127.0.0.1", 4002, 5
app.connect(localhost, port, clientId)

# Start the app on thread
threading.Thread(target=app.run, daemon=True).start()

# Do a single check to confirm connection
while True:
    if isinstance(app.nextOrderId, int):
        print(f"Connected")
        break
    else:
        print(f"Waiting for connection")
        time.sleep(1)

# Define contract
nvda = TradingApp.get_contract("NVDA")

period = 30
requestId = 99

while True:
    # Ask IB for data for our contract
    print(f"Getting data for contract...")
    data = app.get_historical_data(requestId, nvda)

    # We don't have enugh data to compute the donchian
    # channel for period so skip the rest of the code
    if len(data) < period:
        print(
            f"There are only {len(data)} bars of data, skipping..."
        )
        continue

    # Compute the donchian channel
    print(f"Computing the Donchian Channel...")
    donchian = donchian_channel(data, period=period)

    # Get the last traded price
    last_price = data.iloc[-1].close

    # Get the last channel values
    upper, lower = donchian[["upper", "lower"]].iloc[-1]

    print(
        f"Check if last price {last_price} is outside the channels [{upper} and {lower}]"
    )

    # Breakout to the upside
    if last_price >= upper:
        print(f"Breakout detected, going long...")
        # Enter a buy market order for 10 shares
        app.place_order(nvda, "BUY", "MKT", 10)

    # Breakout to the downside
    elif last_price <= lower:
        print(f"Breakout dedected, going short...")
        # Enter a sell market order for 10 shares
        app.place_order(nvda, "SELL", "MKT", 10)