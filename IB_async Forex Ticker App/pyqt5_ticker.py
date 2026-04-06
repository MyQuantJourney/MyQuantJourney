import sys
import asyncio
import PyQt5.QtWidgets as qt
import PyQt5.QtGui as qtgui
import qasync  # Bridges Qt's event loop with Python's asyncio (replaces util.useQt)
from ib_async import IB  # Interactive Brokers async API client
from ib_async.contract import *  # Forex, Stock, Contract classes


class TickerTable(qt.QTableWidget):
    """
    Custom table widget to display real-time market data from IB.
    Maps contract IDs to table rows for efficient updates.
    """
    
    # Column headers - these match Ticker object attributes from ib_async
    headers = [
        "symbol",   # Trading pair (e.g., EURUSD)
        "bidSize",  # Lot size at best bid
        "bid",      # Best buy price
        "ask",      # Best sell price
        "askSize",  # Lot size at best ask
        "last",     # Most recent trade price (lastPrice also works)
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Dictionary mapping IB contract IDs to table row indices
        # This lets us quickly find which row to update when data arrives
        self.conId2Row = {}
        
        # Initialize table structure
        self.setColumnCount(len(self.headers))
        self.setHorizontalHeaderLabels(self.headers)
        self.setAlternatingRowColors(True)  # Easier to read rows

    def __contains__(self, contract):
        """
        Check if a contract is already in the table.
        Used to prevent duplicate subscriptions.
        """
        # conId is IB's unique ID for a contract (0 if not qualified yet)
        return contract.conId and contract.conId in self.conId2Row

    def addTicker(self, ticker):
        """
        Add a new row for a ticker when market data subscription starts.
        Called once per contract when connection is established.
        """
        row = self.rowCount()
        self.insertRow(row)
        self.conId2Row[ticker.contract.conId] = row
        
        # Initialize all cells with "-" 
        for col in range(len(self.headers)):
            item = qt.QTableWidgetItem("-")
            self.setItem(row, col, item)
        
        # Set symbol name in first column
        # For Forex, append currency to avoid confusion (EURUSD.USD)
        item = self.item(row, 0)
        symbol_text = ticker.contract.symbol
        if ticker.contract.secType == "CASH":
            symbol_text += ticker.contract.currency
        item.setText(symbol_text)
        
        self.resizeColumnsToContents()

    def clearTickers(self):
        """Remove all rows and clear the mapping (called on disconnect)"""
        self.setRowCount(0)
        self.conId2Row.clear()

    def onPendingTickers(self, tickers):
        """
        Callback triggered by IB whenever market data updates arrive.
        IB batches updates, so 'tickers' is a set of Ticker objects.
        
        This runs every time the market moves - potentially hundreds of 
        times per second for active pairs.
        """
        for ticker in tickers:
            # Skip if we don't have this contract mapped (shouldn't happen)
            if ticker.contract.conId not in self.conId2Row:
                continue
                
            row = self.conId2Row[ticker.contract.conId]
            
            # Update each column with the corresponding Ticker attribute
            for col, header in enumerate(self.headers):
                if col == 0:
                    continue  # Skip symbol column (already set)
                
                item = self.item(row, col)
                
                # Dynamically get attribute: ticker.bid, ticker.ask, etc.
                # If value is None, display "-" instead
                val = getattr(ticker, header)
                item.setText(str(val) if val is not None else "-")


class Window(qt.QWidget):
    """
    Main application window containing the ticker table, input field,
    connect button, and IB client management.
    """
    
    def __init__(self, host, port, clientId):
        super().__init__()
        
        # ---------- UI Setup ----------
        # Input field for manual symbol entry (e.g., Forex('EURUSD'))
        self.edit = qt.QLineEdit("", self)
        self.edit.editingFinished.connect(self.add)  # Trigger on Enter/loss of focus
        
        # The table widget showing all tickers
        self.table = TickerTable()
        
        # Connect/Disconnect button toggles state
        self.connectButton = qt.QPushButton("Connect")
        self.connectButton.clicked.connect(self.onConnectButtonClicked)
        
        # Layout: Input on top, table in middle, button at bottom
        layout = qt.QVBoxLayout(self)
        layout.addWidget(self.edit)
        layout.addWidget(self.table)
        layout.addWidget(self.connectButton)

        # ---------- IB Setup ----------
        # Connection parameters passed from main()
        self.connectInfo = (host, port, clientId)
        
        # Create IB client instance (not connected yet)
        self.ib = IB()
        
        # Subscribe to pendingTickersEvent - this is how IB pushes updates
        # Whenever market data arrives, IB calls our table's update method
        self.ib.pendingTickersEvent += self.table.onPendingTickers

    def add(self, text=""):
        """
        Add a new contract from the input field.
        Supports any valid Python expression that returns a Contract.
        Examples: Forex('EURUSD'), Stock('AAPL', 'SMART', 'USD')
        """
        text = text or self.edit.text()
        if text:
            try:
                # eval() parses the string into a Contract object
                # SECURITY: Only use this in local/desktop apps, never on web
                contract = eval(text)
                
                if contract:
                    # Schedule async task to qualify and subscribe
                    # (can't block the Qt UI thread)
                    asyncio.create_task(self._add_contract(contract))
            except Exception as e:
                print(f"Error parsing contract: {e}")
            
            self.edit.setText(text)  # Keep text for reference

    async def _add_contract(self, contract):
        """
        Async helper to qualify contracts and request market data.
        
        Qualifying resolves the contract details (conId, exchange, etc.)
        with IB's servers - required before subscribing to data.
        """
        try:
            # qualifyContractsAsync contacts IB to resolve contract details
            qualified = await self.ib.qualifyContractsAsync(contract)
            
            # Check if already in table (prevent duplicates)
            if qualified and contract not in self.table:
                # reqMktData starts the live stream
                # Parameters: contract, genericTickList, snapshot, regulatorySnapshot
                # Empty string means "default tick types", False = streaming (not snapshot)
                ticker = self.ib.reqMktData(contract, "", False, False)
                
                # Add to UI (row will fill with data as it arrives)
                self.table.addTicker(ticker)
        except Exception as e:
            print(f"Error adding contract: {e}")

    def onConnectButtonClicked(self):
        """Toggle connection state when button is clicked"""
        if self.ib.isConnected():
            # Disconnect flow
            self.ib.disconnect()
            self.table.clearTickers()
            self.connectButton.setText("Connect")
        else:
            # Connect flow - must use async task to avoid blocking UI
            asyncio.create_task(self._do_connect())

    async def _do_connect(self):
        """
        Async connection handler.
        Connects to TWS/Gateway, sets data type, and loads default forex pairs.
        """
        try:
            # connectAsync establishes TCP connection and logs in
            # This is where Python 3.14's nest_asyncio would fail without qasync
            await self.ib.connectAsync(*self.connectInfo)
            
            # 2 = Frozen + Realtime (delays realtime data if not subscribed)
            # 1 = Realtime only (requires market data subscription)
            # 3 = Delayed frozen (for testing without subscriptions)
            self.ib.reqMarketDataType(2)
            
            self.connectButton.setText("Disconnect")
            
            # Load default forex pairs on connect
            default_pairs = (
                "EURUSD", "USDJPY", "EURGBP", "USDCAD", 
                "EURCHF", "AUDUSD", "NZDUSD",
            )
            
            for symbol in default_pairs:
                await self._add_contract(Forex(symbol))
                
        except Exception as e:
            print(f"Connection failed: {e}")

    def closeEvent(self, ev):
        """
        Cleanup when window closes.
        Stops the asyncio event loop to allow clean exit.
        """
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.stop()
        # Accept the close event (window actually closes)
        ev.accept()


def main():
    """
    Application entry point.
    Sets up qasync event loop bridging Qt and asyncio.
    """
    # Qt application setup
    app = qt.QApplication(sys.argv)
    
    # Set global font for all widgets
    font = qtgui.QFont("Segoe UI", 11)
    app.setFont(font)
    
    # Create QEventLoop - this allows asyncio code to run inside Qt's loop
    # Without this, IB's async functions would conflict with Qt's event handling
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # Create main window (localhost, TWS paper trading port, client ID 1)
    # Port 7496 for TWS live, 7497 for TWS paper, 4001/4002 for IB Gateway
    window = Window("127.0.0.1", 4002, 1)
    window.resize(600, 400)
    window.show()
    
    # Run until window is closed
    # 'with loop' context manager ensures proper cleanup
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()