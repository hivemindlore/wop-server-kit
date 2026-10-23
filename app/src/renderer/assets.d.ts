// Images the views import; Vite turns them into URLs.
declare module '*.svg' {
  const url: string
  export default url
}
