import os
import logging
from chalice import Chalice, Cron
from chalicelib import utils, trade_processing, trade_execution

app = Chalice(app_name="crypto_bot")
app.log.setLevel(logging.DEBUG)

# REST API Endpoint
@app.route("/receive_trade_signals", methods=["POST"])
def receive_trade_signals():
    """Receives trade signal via post request and executes stop loss or writes it to database."""
    trade_in = app.current_request.json_body
    app.log.debug("Trade Signal Received: %s", trade_in)

    trade_out = trade_processing.preprocess_trade_signal(trade_in)
    app.log.debug("Trade Signal Processed: %s", trade_out)

    if "stop" in trade_out.get("order_comment").lower():
        secret_name = os.environ.get("SECRET_NAME")
        exchange_name = os.environ.get("EXCHANGE_NAME")
        base_currency = os.environ.get("BASE_CURRENCY")
        sandbox = utils.get_env_var("SANDBOX")

        exchange = trade_execution.Exchange(exchange_name, base_currency)
        exchange.connect(secret_name, sandbox=sandbox)
        app.log.debug(f"Succesfully connected to exchange: {exchange_name}")

        order = trade_execution.execute_long_stop(exchange, trade_out, increment_pct=0.001)
        app.log.info(f"Successfully executed stop loss order: {order}")
    else:
        table_name = os.environ.get("TABLE_NAME")
        dynamodb_manager = utils.DynamoDBManager()
        table = dynamodb_manager.get_table(table_name)
        app.log.debug("Established connection to %s database", table_name)

        table.put_item(Item=trade_out)
        app.log.info("Trade on %s at %s saved to database.", trade_out['ticker'], trade_out['create_ts'])

# Scheduled Lambda Function 
@app.schedule(Cron("1", "0,8,16", "*", "*", "?", "*"))
def execute_trade_signals(event):
    table_name = os.environ.get("TABLE_NAME")
    utcnow = utils.get_utc_now_rounded()
    trades = trade_processing.get_all_recent_signals(utcnow, table_name)
    if trades:
        app.log.debug(f"Succesfully retrieved trade signals from database: {trades}")

        secret_name = os.environ.get("SECRET_NAME")
        exchange_name = os.environ.get("EXCHANGE_NAME")
        base_currency = os.environ.get("BASE_CURRENCY")
        sandbox = utils.get_env_var("SANDBOX")

        exchange = trade_execution.Exchange(exchange_name, base_currency)
        exchange.connect(secret_name, sandbox=sandbox)
        app.log.debug(f"Succesfully connected to exchange: {exchange_name}")

        orders = trade_execution.buy_side_boost(exchange, trades, increment_pct=0.001)
        if orders:
            app.log.info(f"Successfully placed order(s): {orders}")
    else:
        app.log.info(f"No trade signals at {utcnow}")
