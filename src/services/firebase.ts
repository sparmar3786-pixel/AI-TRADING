import { FirebaseApp, getApp, getApps, initializeApp } from 'firebase/app';
import { getAuth, signInAnonymously } from 'firebase/auth';
import {
  Firestore,
  collection,
  doc,
  getDocs,
  getFirestore,
  limit,
  query,
  serverTimestamp,
  setDoc,
  where,
} from 'firebase/firestore';
import { PaperTrade } from '../types/market';

const env = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env ?? {};

export const firebaseConfig = {
  apiKey: env.VITE_FIREBASE_API_KEY?.trim() ?? '',
  authDomain: env.VITE_FIREBASE_AUTH_DOMAIN?.trim() ?? '',
  projectId: env.VITE_FIREBASE_PROJECT_ID?.trim() ?? '',
  storageBucket: env.VITE_FIREBASE_STORAGE_BUCKET?.trim() ?? '',
  messagingSenderId: env.VITE_FIREBASE_MESSAGING_SENDER_ID?.trim() ?? '',
  appId: env.VITE_FIREBASE_APP_ID?.trim() ?? '',
};

const configuredDatabaseId = env.VITE_FIRESTORE_DATABASE_ID?.trim() ?? '';
export const FIRESTORE_DATABASE_ID = configuredDatabaseId || '(default)';

const firebaseConfigured = Object.values(firebaseConfig).every(value => value.length > 0);
let firebaseApp: FirebaseApp | null = null;
let firestoreDb: Firestore | null = null;

if (firebaseConfigured) {
  try {
    firebaseApp = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);
    firestoreDb = configuredDatabaseId
      ? getFirestore(firebaseApp, configuredDatabaseId)
      : getFirestore(firebaseApp);
  } catch (error) {
    // Cloud sync is optional: a Firebase configuration error must not crash the terminal.
    console.warn('Firebase cloud sync unavailable; continuing offline.', error);
    firebaseApp = null;
    firestoreDb = null;
  }
} else {
  console.info('Firebase is not configured; cloud paper-trade sync is disabled.');
}

export const db: Firestore | null = firestoreDb;

/**
 * Return the current Firebase UID, creating an anonymous session when needed.
 * Anonymous auth must be enabled in the Firebase console; otherwise cloud sync
 * remains unavailable and local paper trading continues to work.
 */
async function getAuthenticatedUid(): Promise<string | null> {
  if (!firebaseApp) return null;
  try {
    const auth = getAuth(firebaseApp);
    const user = auth.currentUser ?? (await signInAnonymously(auth)).user;
    return user.uid || null;
  } catch (error) {
    console.warn('Firebase authentication unavailable; cloud sync skipped.', error);
    return null;
  }
}

/**
 * Return a Firebase ID token for APIs that perform server-side UID allow-list checks.
 * The token is short-lived and is sent only in the Authorization header; it is
 * never persisted by this module. Anonymous auth is accepted only if the backend
 * explicitly allow-lists that verified UID.
 */
export async function getBackendIdToken(): Promise<string | null> {
  if (!firebaseApp) return null;
  try {
    const auth = getAuth(firebaseApp);
    const user = auth.currentUser ?? (await signInAnonymously(auth)).user;
    return await user.getIdToken();
  } catch (error) {
    console.warn('Backend Firebase authentication unavailable.', error);
    return null;
  }
}

/**
 * Sync a paper trade only under the authenticated Firebase UID expected by
 * firestore.rules. Cloud failures never interrupt local paper trading.
 */
export async function syncTradeToCloud(trade: PaperTrade, deviceId: string) {
  if (!db) return;
  try {
    const userId = await getAuthenticatedUid();
    if (!userId) return;
    const tradeRef = doc(db, 'paper_trades', `${userId}_${trade.id}`);
    await setDoc(tradeRef, {
      ...trade,
      userId,
      deviceId,
      syncedAt: serverTimestamp(),
      updatedAt: new Date().toISOString(),
    }, { merge: true });
  } catch (err) {
    console.debug('Firebase paper trade sync notice:', err);
  }
}

/**
 * Fetch only the current authenticated user's cloud trades.
 * Sort locally to avoid requiring a composite Firestore index for this query.
 */
export async function fetchCloudTrades(): Promise<PaperTrade[]> {
  if (!db) return [];
  try {
    const userId = await getAuthenticatedUid();
    if (!userId) return [];
    const q = query(
      collection(db, 'paper_trades'),
      where('userId', '==', userId),
      limit(50),
    );
    const snap = await getDocs(q);
    const trades: PaperTrade[] = [];
    snap.forEach(docSnap => {
      trades.push(docSnap.data() as PaperTrade);
    });
    return trades.sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
  } catch (error) {
    console.debug('Firebase paper trade fetch unavailable:', error);
    return [];
  }
}
