import { computed, ref } from 'vue'
import { apiFetch } from './api'

const currentUser = ref(null)
const loaded = ref(false)

export function resetCurrentUserCache() {
  currentUser.value = null
  loaded.value = false
}

export async function loadCurrentUser(force = false) {
  if (loaded.value && !force) return currentUser.value
  try {
    const res = await apiFetch('/api/auth/me/')
    if (!res.ok) {
      currentUser.value = null
      loaded.value = true
      return null
    }
    currentUser.value = await res.json()
    loaded.value = true
    return currentUser.value
  } catch {
    currentUser.value = null
    loaded.value = true
    return null
  }
}

export const isAdminUser = computed(() => {
  const u = currentUser.value || {}
  return Boolean(u.is_staff || u.is_superuser)
})

export function useCurrentUser() {
  return {
    currentUser,
    isAdminUser,
    loadCurrentUser,
    resetCurrentUserCache,
  }
}
