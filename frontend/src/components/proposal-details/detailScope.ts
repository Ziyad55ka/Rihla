import { createContext, useContext } from 'react'

export const DetailScope = createContext('')

export function useDetailId() {
  const prefix = useContext(DetailScope)
  return (id: string) => prefix ? `${prefix}-${id}` : id
}
