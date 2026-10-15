import { initializeApp, getApps, getApp } from 'firebase/app';
import {
  getFirestore,
  collection,
  doc,
  setDoc,
  getDocs,
  query,
  orderBy,
  limit,
  serverTimestamp,
} from 'firebase/firestore';
import { PaperTrade } from '../types/market';

const env = (import.meta as any).env || {};

export const firebaseConfig = {
  apiKey: env.VITE_FIREBASE_API_KEY || 'AIzaSyBQI3jf_RlgapjR1FX95Z0y6LQZ1HsXb1w',
  authDomain: env.VITE_FIREBASE_AUTH_DOMAIN || 'project-d55f227e-a5a3-4161-b06.firebaseapp.com',
  projectId: env.VITE_FIREBASE_PROJECT_ID || 'project-d55f227e-a5a3-4161-b06',
  storageBucket: env.VITE_FIREBASE_STORAGE_BUCKET || 'project-d55f227e-a5a3-4161-b06.firebasestorage.app',
  messagingSenderId: env.VITE_FIREBASE_MESSAGING_SENDER_ID || '937795693519',
  appId: env.VITE_FIREBASE_APP_ID || '1:937795693519:android:5df61a6227bd8e250b80ba',
};

export const FIRESTORE_DATABASE_ID = 'ai-studio-android-aitradin-e7389ca7-bc19-45aa-98a6-f0fe07c8611b';

// Initialize Firebase
const app = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);

let firestoreDb = null;
try {
  firestoreDb = getFirestore(app, FIRESTORE_DATABASE_ID);
} catch {
  try {
    firestoreDb = getFirestore(app);
  } catch (e) {
    console.warn('Firestore initialization fallback:', e);
  }
}

export const db = firestoreDb;

/**
 * Sync paper trade to Cloud Firestore (Free Firebase integration)
 */
export async function syncTradeToCloud(trade: PaperTrade, deviceId: string) {
  if (!db) return;
  try {
    const tradeRef = doc(db, 'paper_trades', trade.id);
    await setDoc(tradeRef, {
      ...trade,
      deviceId,
      syncedAt: serverTimestamp(),
      updatedAt: new Date().toISOString(),
    }, { merge: true });
  } catch (err) {
    // Graceful offline fallback
    console.debug('Firebase paper trade sync notice:', err);
  }
}

/**
 * Fetch past cloud trades
 */
export async function fetchCloudTrades(): Promise<PaperTrade[]> {
  if (!db) return [];
  try {
    const q = query(collection(db, 'paper_trades'), orderBy('timestamp', 'desc'), limit(50));
    const snap = await getDocs(q);
    const trades: PaperTrade[] = [];
    snap.forEach(docSnap => {
      trades.push(docSnap.data() as PaperTrade);
    });
    return trades;
  } catch {
    return [];
  }
}
