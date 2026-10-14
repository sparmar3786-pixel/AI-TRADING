import { initializeApp, getApps, getApp, type FirebaseApp } from 'firebase/app';
import { 
  getFirestore, 
  collection, 
  doc, 
  getDocs, 
  setDoc, 
  addDoc, 
  query, 
  where, 
  orderBy, 
  onSnapshot, 
  serverTimestamp,
  type Firestore,
  type DocumentData,
  type Unsubscribe
} from 'firebase/firestore';
import { 
  getAuth, 
  GoogleAuthProvider, 
  signInWithPopup, 
  signOut as fbSignOut, 
  onAuthStateChanged,
  type Auth,
  type User as FirebaseUser
} from 'firebase/auth';

export const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "AIzaSyBQI3jf_RlgapjR1FX95Z0y6LQZ1HsXb1w",
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "project-d55f227e-a5a3-4161-b06.firebaseapp.com",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "project-d55f227e-a5a3-4161-b06",
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || "project-d55f227e-a5a3-4161-b06.firebasestorage.app",
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "937795693519",
  appId: import.meta.env.VITE_FIREBASE_APP_ID || "1:937795693519:android:5df61a6227bd8e250b80ba"
};

export const FIRESTORE_DATABASE_ID = "ai-studio-android-aitradin-e7389ca7-bc19-45aa-98a6-f0fe07c8611b";

// Initialize Firebase App
export const app: FirebaseApp = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);

// Initialize Firestore (attempt specific custom database ID, fallback to default if not configured)
let firestoreInstance: Firestore;
try {
  firestoreInstance = getFirestore(app, FIRESTORE_DATABASE_ID);
} catch (e) {
  console.warn("Falling back to default Firestore database", e);
  firestoreInstance = getFirestore(app);
}

export const db: Firestore = firestoreInstance;
export const auth: Auth = getAuth(app);
export const googleAuthProvider = new GoogleAuthProvider();

export interface FirebaseTradeRecord {
  id?: string;
  userId: string;
  symbol: string;
  action: 'BUY' | 'SELL';
  shares: number;
  price: number;
  totalValue: number;
  status: 'executed' | 'approved' | 'pending' | 'rejected';
  agent: string;
  reasoning: string;
  createdAt: string;
  executedAt?: string;
  realizedPnl?: number;
  returnPercent?: number;
  sourceType: 'analysis' | 'rebalance' | 'manual';
  broker?: string;
  orderId?: string;
}

// Collection reference for trades
export const TRADES_COLLECTION = 'trading_actions';
export const PORTFOLIO_COLLECTION = 'user_portfolios';
export const SETTINGS_COLLECTION = 'user_settings';

/**
 * Save trade to Firestore
 */
export async function saveTradeToFirestore(trade: Omit<FirebaseTradeRecord, 'id'>): Promise<string> {
  try {
    const colRef = collection(db, TRADES_COLLECTION);
    const docRef = await addDoc(colRef, {
      ...trade,
      serverCreatedAt: serverTimestamp(),
      updatedAt: new Date().toISOString()
    });
    return docRef.id;
  } catch (error) {
    console.error('Error saving trade to Firestore:', error);
    throw error;
  }
}

/**
 * Fetch trades from Firestore for a given user and date range
 */
export async function getTradesFromFirestore(
  userId?: string, 
  fromDate?: Date, 
  toDate?: Date
): Promise<FirebaseTradeRecord[]> {
  try {
    const colRef = collection(db, TRADES_COLLECTION);
    let q = query(colRef, orderBy('createdAt', 'desc'));

    if (userId) {
      q = query(colRef, where('userId', '==', userId), orderBy('createdAt', 'desc'));
    }

    const snapshot = await getDocs(q);
    const trades: FirebaseTradeRecord[] = [];

    snapshot.forEach((docSnapshot) => {
      const data = docSnapshot.data() as DocumentData;
      const tradeDate = new Date(data.createdAt || Date.now());

      // Client-side date filter if needed
      if (fromDate && tradeDate < fromDate) return;
      if (toDate && tradeDate > toDate) return;

      trades.push({
        id: docSnapshot.id,
        userId: data.userId || '',
        symbol: data.symbol || data.ticker || 'UNKNOWN',
        action: data.action || 'BUY',
        shares: Number(data.shares || data.quantity || 1),
        price: Number(data.price || 0),
        totalValue: Number(data.totalValue || (Number(data.shares || 1) * Number(data.price || 0))),
        status: data.status || 'executed',
        agent: data.agent || 'AI Quant Engine',
        reasoning: data.reasoning || '',
        createdAt: data.createdAt || new Date().toISOString(),
        executedAt: data.executedAt,
        realizedPnl: data.realizedPnl !== undefined ? Number(data.realizedPnl) : undefined,
        returnPercent: data.returnPercent !== undefined ? Number(data.returnPercent) : undefined,
        sourceType: data.sourceType || 'analysis',
        broker: data.broker,
        orderId: data.orderId
      });
    });

    return trades;
  } catch (error) {
    console.warn('Error fetching trades from Firestore:', error);
    return [];
  }
}

/**
 * Real-time listener for Firestore trades
 */
export function subscribeToFirestoreTrades(
  userId: string | undefined,
  onUpdate: (trades: FirebaseTradeRecord[]) => void,
  onError?: (err: Error) => void
): Unsubscribe {
  try {
    const colRef = collection(db, TRADES_COLLECTION);
    const q = userId 
      ? query(colRef, where('userId', '==', userId), orderBy('createdAt', 'desc'))
      : query(colRef, orderBy('createdAt', 'desc'));

    return onSnapshot(
      q, 
      (snapshot) => {
        const trades: FirebaseTradeRecord[] = [];
        snapshot.forEach((docSnapshot) => {
          const data = docSnapshot.data() as DocumentData;
          trades.push({
            id: docSnapshot.id,
            userId: data.userId || '',
            symbol: data.symbol || data.ticker || 'UNKNOWN',
            action: data.action || 'BUY',
            shares: Number(data.shares || 1),
            price: Number(data.price || 0),
            totalValue: Number(data.totalValue || 0),
            status: data.status || 'executed',
            agent: data.agent || 'AI Quant Engine',
            reasoning: data.reasoning || '',
            createdAt: data.createdAt || new Date().toISOString(),
            executedAt: data.executedAt,
            realizedPnl: data.realizedPnl,
            returnPercent: data.returnPercent,
            sourceType: data.sourceType || 'analysis',
            broker: data.broker,
            orderId: data.orderId
          });
        });
        onUpdate(trades);
      },
      (err) => {
        console.warn('Firestore subscription error:', err);
        if (onError) onError(err);
      }
    );
  } catch (error) {
    console.warn('Failed to subscribe to Firestore:', error);
    return () => {};
  }
}

/**
 * Seed initial sample trades in Firestore if the database collection is empty
 */
export async function seedInitialFirestoreTrades(userId: string): Promise<number> {
  try {
    const existing = await getTradesFromFirestore(userId);
    if (existing.length > 0) return 0;

    const sampleTrades: Omit<FirebaseTradeRecord, 'id'>[] = [
      {
        userId,
        symbol: 'NVDA',
        action: 'BUY',
        shares: 15,
        price: 118.25,
        totalValue: 1773.75,
        status: 'executed',
        agent: 'Confluence Trend Agent',
        reasoning: 'Bullish breakout above key volume shelf with strong momentum continuation.',
        createdAt: new Date(Date.now() - 14 * 86400000).toISOString(),
        executedAt: new Date(Date.now() - 14 * 86400000).toISOString(),
        realizedPnl: 245.50,
        returnPercent: 13.84,
        sourceType: 'analysis'
      },
      {
        userId,
        symbol: 'AAPL',
        action: 'BUY',
        shares: 20,
        price: 221.50,
        totalValue: 4430.00,
        status: 'executed',
        agent: 'Mean Reversion Agent',
        reasoning: 'RSI oversold rebound supported by institutional block order accumulation.',
        createdAt: new Date(Date.now() - 10 * 86400000).toISOString(),
        executedAt: new Date(Date.now() - 10 * 86400000).toISOString(),
        realizedPnl: 180.20,
        returnPercent: 4.07,
        sourceType: 'analysis'
      },
      {
        userId,
        symbol: 'TSLA',
        action: 'SELL',
        shares: 10,
        price: 248.80,
        totalValue: 2488.00,
        status: 'executed',
        agent: 'Risk Manager Agent',
        reasoning: 'Target resistance level reached; locking in algorithmic profit before options expiry.',
        createdAt: new Date(Date.now() - 5 * 86400000).toISOString(),
        executedAt: new Date(Date.now() - 5 * 86400000).toISOString(),
        realizedPnl: 312.40,
        returnPercent: 12.56,
        sourceType: 'rebalance'
      },
      {
        userId,
        symbol: 'MSFT',
        action: 'BUY',
        shares: 8,
        price: 432.10,
        totalValue: 3456.80,
        status: 'executed',
        agent: 'Macro Quant Agent',
        reasoning: 'Cloud infrastructure growth surge alignment with predictive earnings model.',
        createdAt: new Date(Date.now() - 2 * 86400000).toISOString(),
        executedAt: new Date(Date.now() - 2 * 86400000).toISOString(),
        realizedPnl: 95.80,
        returnPercent: 2.77,
        sourceType: 'analysis'
      }
    ];

    for (const trade of sampleTrades) {
      await saveTradeToFirestore(trade);
    }

    return sampleTrades.length;
  } catch (e) {
    console.warn('Could not seed initial Firestore trades:', e);
    return 0;
  }
}
