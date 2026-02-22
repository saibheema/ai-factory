/**
 * Firebase config + auth helpers for AI Factory.
 *
 * Firebase project: unicon-494419  (AI Factory Web app)
 */
import { initializeApp } from 'firebase/app'
import {
  getAuth,
  GoogleAuthProvider,
  signInWithRedirect,
  getRedirectResult,
  signOut,
  onAuthStateChanged,
} from 'firebase/auth'

const firebaseConfig = {
  apiKey: 'AIzaSyCSv_MrpciLJDGFmLZySNWx1faD0GkaLds',
  authDomain: 'unicon-494419.firebaseapp.com',
  projectId: 'unicon-494419',
  storageBucket: 'unicon-494419.firebasestorage.app',
  messagingSenderId: '664984131730',
  appId: '1:664984131730:web:5f48b8a845b2e5377eae4b',
  measurementId: 'G-7F4S15GF51',
}

const app = initializeApp(firebaseConfig)
const auth = getAuth(app)
const googleProvider = new GoogleAuthProvider()

export { auth }

/* Handle redirect result when page reloads after Google sign-in */
getRedirectResult(auth).catch(() => { /* ignore — user not returning from redirect */ })

export async function signInWithGoogle() {
  await signInWithRedirect(auth, googleProvider)
  /* Page navigates away — control returns via onAuthChange after redirect back */
}

export async function logOut() {
  await signOut(auth)
}

export function onAuthChange(callback) {
  return onAuthStateChanged(auth, callback)
}

export async function getIdToken() {
  const user = auth.currentUser
  if (!user) return null
  return user.getIdToken()
}
