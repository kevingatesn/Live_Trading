import yfinance as yf
import pandas as pd
import numpy as np
import ta
import logging
import matplotlib.pyplot as plt
import os
from datetime import datetime
from state_manager import PortfolioManager

# ==========================
# 1. CONFIGURATION DU JOURNAL DE BORD (LOGGER)
# ==========================
logging.basicConfig(
    filename='bot_execution.log',
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# On force aussi l'affichage dans la console pour ton confort
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)

# ==========================
# 2. LE MOTEUR DE DÉCISION LIVE
# ==========================
class LiveDecisionEngine:
    def __init__(self):
        self.assets = ["BTC-USD", "ETH-USD", "SPY", "GC=F"]
        self.risk_per_trade = 0.02
        self.max_global_risk = 0.06
        self.max_positions = int(self.max_global_risk / self.risk_per_trade)
        
        # Connexion à notre système de mémoire
        self.portfolio = PortfolioManager("live_paper_trading.json")
        logging.info("--- DÉMARRAGE DE LA ROUTINE DE TRADING LIVE ---")

    def fetch_market_data(self):
        """Télécharge et prépare les données récentes pour chaque actif."""
        market_data = {}
        logging.info("Téléchargement des données de marché (100 derniers jours)...")
        
        for asset in self.assets:
            # On prend 100 jours pour être sûr de pouvoir calculer la MA 50 et l'ADX 14 correctement
            df = yf.download(asset, period="100d", interval="1d", progress=False)
            
            if df.empty:
                logging.warning(f"Impossible de récupérer les données pour {asset}.")
                continue
                
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
                
            df = df[["Open","High","Low","Close"]].dropna()
            
            # Calcul des indicateurs du système
            df['Max_50'] = df['High'].rolling(window=50).max().shift(1)
            df['Min_20'] = df['Low'].rolling(window=20).min().shift(1)
            
            adx_indicator = ta.trend.ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14)
            df['ADX'] = adx_indicator.adx().shift(1)
            
            market_data[asset] = df
            
        return market_data

    def run_daily_execution(self):
        """La boucle logique exécutée une fois par jour."""
        market_data = self.fetch_market_data()
        
        # ÉVALUATION DES SORTIES (Priorité 1 : Couper les pertes / Prendre les profits)
        for asset, data in market_data.items():
            if self.portfolio.get_position(asset):
                current_price = data['Close'].iloc[-1]
                min_20 = data['Min_20'].iloc[-1]
                
                logging.info(f"[{asset}] SURVEILLANCE : Prix={current_price:.2f}$, StopLoss(Min20)={min_20:.2f}$")
                
                if current_price < min_20:
                    logging.warning(f"[{asset}] CASSURE DU SUPPORT DÉTECTÉE ! Exécution de la Vente.")
                    self.portfolio.execute_sell(asset, current_price)
        
        # ÉVALUATION DES ENTRÉES (Priorité 2 : Chercher de nouvelles tendances)
        for asset, data in market_data.items():
            if not self.portfolio.get_position(asset):
                current_price = data['Close'].iloc[-1]
                max_50 = data['Max_50'].iloc[-1]
                adx_val = data['ADX'].iloc[-1]
                
                # Vérifier si on a le droit de trader (Plafond de risque)
                if self.portfolio.get_active_positions_count() >= self.max_positions:
                    logging.info(f"[{asset}] Signal ignoré : Plafond de risque atteint ({self.max_positions} positions max).")
                    continue
                
                # LA LOGIQUE D'ATTAQUE
                if current_price > max_50:
                    if adx_val > 25:
                        logging.info(f"[{asset}] SIGNAL D'ACHAT VALIDÉ : Breakout ({current_price:.2f}$ > {max_50:.2f}$) & ADX fort ({adx_val:.2f})")
                        
                        # Calcul de la taille de position institutionnelle
                        stop_price = data['Min_20'].iloc[-1]
                        portfolio_value = self.portfolio.get_cash() # Simplification pour le paper trading
                        risk_amount = portfolio_value * self.risk_per_trade
                        risk_per_coin = current_price - stop_price
                        
                        if risk_per_coin > 0:
                            qty = risk_amount / risk_per_coin
                            # Sécurité cash
                            max_qty = self.portfolio.get_cash() / current_price
                            qty = min(qty, max_qty)
                            
                            self.portfolio.execute_buy(asset, current_price, qty)
                    else:
                        logging.info(f"[{asset}] FAUSSE CASSURE : Prix > Max 50, mais ADX trop faible ({adx_val:.2f} < 25). Marché en range, on filtre.")

                else:
                    # AJOUT : Le bot nous dit qu'il a scanné, mais que la résistance est loin.
                    logging.info(f"[{asset}] SCAN QUOTIDIEN : Prix ({current_price:.2f}$) sous la résistance ({max_50:.2f}$). On reste liquide.")
                    
        # À la fin de l'exécution, on met à jour le visuel silencieusement
        self.generate_live_dashboard(market_data)
        logging.info("--- FIN DE LA ROUTINE QUOTIDIENNE ---")

    def generate_live_dashboard(self, market_data):
        """Génère une image PNG de l'état du portefeuille sans bloquer le script."""
        logging.info("Génération du Dashboard visuel (dashboard_live.png)...")
        
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.axis('off') # On cache les axes pour faire un tableau de bord texte/visuel
        
        cash = self.portfolio.get_cash()
        positions = self.portfolio.state["positions"]
        
        texte_dashboard = f"DASHBOARD LIVE - PAPER TRADING\nDate de mise a jour : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        texte_dashboard += "="*50 + "\n"
        texte_dashboard += f"CASH DISPONIBLE : {cash:.2f} $\n"
        texte_dashboard += f"POSITIONS ACTIVES : {len(positions)} / {self.max_positions}\n\n"
        
        portfolio_value = cash
        
        if len(positions) == 0:
            texte_dashboard += "Aucune position en cours. Le bot attend une tendance.\n"
        else:
            for asset, pos_data in positions.items():
                qty = pos_data["qty"]
                entry = pos_data["entry_price"]
                
                # Récupérer le prix actuel si dispo dans market_data
                current_price = entry 
                if asset in market_data:
                    current_price = market_data[asset]['Close'].iloc[-1]
                
                valeur_actuelle = qty * current_price
                portfolio_value += valeur_actuelle
                pnl_latent = (current_price / entry - 1) * 100
                
                texte_dashboard += f"-> {asset} : Qty: {qty:.4f} | Entrée: {entry:.2f}$ | Actuel: {current_price:.2f}$ | PnL: {pnl_latent:.2f}%\n"

        texte_dashboard += "="*50 + "\n"
        texte_dashboard += f"VALEUR GLOBALE ESTIMEE : {portfolio_value:.2f} $\n"

        # Ajouter le texte sur l'image
        plt.text(0.05, 0.95, texte_dashboard, fontsize=12, family='monospace', va='top', ha='left', 
                 bbox=dict(facecolor='black', alpha=0.8, edgecolor='none', boxstyle='round,pad=1'), color='lime')
        
        plt.tight_layout()
        plt.savefig('dashboard_live.png', facecolor='black', dpi=150)
        plt.close(fig) # Libère la mémoire, le bot ne plante pas !

# ==========================
# 3. LANCEMENT MANUEL POUR TEST
# ==========================
if __name__ == "__main__":
    bot = LiveDecisionEngine()
    bot.run_daily_execution()