package web

import (
	"embed"
	"html/template"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/subdavis/kobo-book-downloader/internal/config"
)

//go:embed templates/*
var templateFS embed.FS

// Server holds the gin engine and dependencies.
type Server struct {
	engine    *gin.Engine
	store     *config.Store
	outputDir string
	tmpl      *template.Template
}

func New(store *config.Store, outputDir string, debug bool) *Server {
	if !debug {
		gin.SetMode(gin.ReleaseMode)
	}

	tmpl := template.Must(template.ParseFS(templateFS, "templates/*.html"))

	e := gin.Default()
	e.SetHTMLTemplate(tmpl)

	s := &Server{engine: e, store: store, outputDir: outputDir, tmpl: tmpl}
	s.registerRoutes()
	return s
}

func (s *Server) Run(addr string) error {
	return s.engine.Run(addr)
}

func (s *Server) Handler() http.Handler {
	return s.engine
}

func (s *Server) registerRoutes() {
	e := s.engine

	e.GET("/", func(c *gin.Context) { c.Redirect(http.StatusFound, "/user") })

	e.GET("/user", s.listUsers)
	e.POST("/user", s.initiateLogin)
	e.POST("/user/check-activation", s.checkActivation)
	e.POST("/user/:userid/remove", s.removeUser)
	e.GET("/user/:userid/book", s.userBooks)
	e.GET("/user/:userid/book/:productid", s.downloadBook)
	e.GET("/book", s.allBooks)
}
