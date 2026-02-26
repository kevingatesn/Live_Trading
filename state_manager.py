import json
import os
from datetime import datetime

class PortfolioManager:
    def __init__(self, filename="portfolio_state.json", initial_capital=10000.0):
        self.filename = filename
        self.initial_capital = initial_capital
        self.state = self._load_or_create()

    def _load_or_create(self):
        """Charge le portefeuille existant ou en crée un vierge si c'est le premier lancement."""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    print(f"[*] Chargement de la mémoire depuis {self.filename}")
                    return json.load(f)
            except json.JSONDecodeError:
                # Si on arrive ici, c'est que quelqu'un a modifié le fichier à la main et l'a cassé
                print("ERREUR CRITIQUE : Le fichier JSON est corrompu. Intervention manuelle requise.")
                exit(1)
        else:
            print("[!] Aucun historique trouvé. Initialisation d'un nouveau portefeuille.")
            default_state = {
                "cash": self.initial_capital,
                "positions": {}, # Dictionnaire vide pour accueillir les actifs
                "history": [],   # Historique des trades fermés pour calculer nos stats
                "last_updated": str(datetime.now())
            }
            self._save(default_state)
            return default_state

    def _save(self, state_dict):
        """Sauvegarde l'état de manière atomique pour éviter toute corruption."""
        temp_file = self.filename + ".tmp"
        state_dict["last_updated"] = str(datetime.now())
        
        # 1. Écriture dans un fichier temporaire
        with open(temp_file, 'w') as f:
            json.dump(state_dict, f, indent=4)
        
        # 2. Remplacement atomique de l'ancien fichier
        os.replace(temp_file, self.filename)
        self.state = state_dict

    def get_cash(self):
        return self.state["cash"]

    def get_active_positions_count(self):
        return len(self.state["positions"])

    def get_position(self, asset):
        return self.state["positions"].get(asset, None)

    def execute_buy(self, asset, price, qty, fee_rate=0.0015):
        """Inscrit un achat dans la mémoire et déduit le cash."""
        cost = qty * price
        fee = cost * fee_rate
        total_deduction = cost + fee

        if total_deduction > self.state["cash"]:
            print(f"[ERREUR] Cash insuffisant pour acheter {asset}. Annulation.")
            return False

        # Mise à jour de la mémoire
        self.state["cash"] -= total_deduction
        self.state["positions"][asset] = {
            "qty": qty,
            "entry_price": price,
            "entry_date": str(datetime.now())
        }
        
        self._save(self.state)
        print(f"[ACHAT VALIDÉ] {qty:.4f} {asset} à {price:.2f}$ | Cash restant : {self.state['cash']:.2f}$")
        return True

    def execute_sell(self, asset, price, fee_rate=0.0015):
        """Inscrit une vente, libère le cash et archive le trade."""
        if asset not in self.state["positions"]:
            print(f"[ERREUR] Tentative de vente de {asset} qui n'est pas en portefeuille.")
            return False

        position = self.state["positions"][asset]
        qty = position["qty"]
        entry_price = position["entry_price"]

        gross_value = qty * price
        fee = gross_value * fee_rate
        net_value = gross_value - fee
        
        pnl_net = net_value - (qty * entry_price) # Profit and Loss

        # Mise à jour de la mémoire
        self.state["cash"] += net_value
        
        # Archiver le trade pour nos statistiques
        self.state["history"].append({
            "asset": asset,
            "entry_price": entry_price,
            "exit_price": price,
            "pnl_net": pnl_net,
            "exit_date": str(datetime.now())
        })
        
        # Supprimer la position active
        del self.state["positions"][asset]
        
        self._save(self.state)
        print(f"[VENTE VALIDÉE] {asset} à {price:.2f}$ | PnL : {pnl_net:.2f}$ | Cash : {self.state['cash']:.2f}$")
        return True
    
if __name__ == "__main__":
    # Test du système de mémoire
    portfolio = PortfolioManager("test_paper_trading.json")
    
    # Simuler un achat de Bitcoin
    if not portfolio.get_position("BTC-USD"):
        portfolio.execute_buy("BTC-USD", price=60000.0, qty=0.05)
    
    # Simuler une vente le lendemain
    portfolio.execute_sell("BTC-USD", price=65000.0)