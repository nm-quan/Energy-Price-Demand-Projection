export const setToken = (token) => localStorage.setItem('broker_token', token);
export const getToken = () => localStorage.getItem('broker_token');
export const removeToken = () => localStorage.removeItem('broker_token');
export const isAuthenticated = () => !!getToken();
