package web

import (
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"sort"

	"github.com/gin-gonic/gin"
	"github.com/subdavis/kobo-book-downloader/internal/actions"
	"github.com/subdavis/kobo-book-downloader/internal/config"
)

const (
	booksTemplate = "books.html"
	errorTemplate = "error.html"
)

func (s *Server) listUsers(c *gin.Context) {
	c.HTML(http.StatusOK, "users.html", gin.H{
		"Users": s.store.UserList.Users,
	})
}

func (s *Server) initiateLogin(c *gin.Context) {
	email := c.PostForm("email")
	if email == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "email is required"})
		return
	}

	u := &config.User{Email: email}
	pollURL, code, err := actions.InitiateLogin(u, s.store)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Stash the partially-constructed user so CheckActivation can finish it.
	s.store.UserList.Users = append(s.store.UserList.Users, u)
	if err := s.store.Save(); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"activation_url":  "https://www.kobo.com/activate",
		"activation_code": code,
		"check_url":       pollURL,
		"email":           email,
		"user_id":         u.UserId,
	})
}

func (s *Server) checkActivation(c *gin.Context) {
	var body struct {
		CheckURL string `json:"check_url"`
		Email    string `json:"email"`
	}
	if err := c.ShouldBindJSON(&body); err != nil || body.CheckURL == "" || body.Email == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "check_url and email are required"})
		return
	}

	// Find the pending user by email.
	u := s.store.UserList.Get(body.Email)
	if u == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "user not found"})
		return
	}

	done, err := actions.CheckActivation(u, s.store, body.CheckURL)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": done})
}

func (s *Server) removeUser(c *gin.Context) {
	u := s.lookupUser(c)
	if u == nil {
		return
	}
	s.store.UserList.Remove(u)
	if err := s.store.Save(); err != nil {
		c.HTML(http.StatusInternalServerError, errorTemplate, gin.H{"Error": err.Error()})
		return
	}
	c.Redirect(http.StatusFound, "/user")
}

func (s *Server) userBooks(c *gin.Context) {
	u := s.lookupUser(c)
	if u == nil {
		return
	}
	books, err := actions.ListBooks([]*config.User{u}, s.store, false)
	if err != nil {
		c.HTML(http.StatusInternalServerError, booksTemplate, gin.H{"Error": err.Error()})
		return
	}
	sort.Slice(books, func(i, j int) bool { return books[i].Title < books[j].Title })
	c.HTML(http.StatusOK, booksTemplate, gin.H{
		"Books":  books,
		"UserId": c.Param("userid"),
	})
}

func (s *Server) downloadBook(c *gin.Context) {
	u := s.lookupUser(c)
	if u == nil {
		return
	}
	productId := c.Param("productid")

	if err := os.MkdirAll(s.outputDir, 0o755); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	outPath, err := actions.GetBookOrBooks(u, s.store, s.outputDir, "", productId, func(msg string) {
		fmt.Println(msg)
	})
	if err != nil {
		c.HTML(http.StatusInternalServerError, errorTemplate, gin.H{"Error": err.Error()})
		return
	}
	if outPath == "" {
		c.HTML(http.StatusNotFound, errorTemplate, gin.H{"Error": "book not found or cannot be downloaded"})
		return
	}

	dir, file := filepath.Split(outPath)
	c.FileAttachment(filepath.Join(dir, file), file)
}

func (s *Server) allBooks(c *gin.Context) {
	books, err := actions.ListBooks(s.store.UserList.Users, s.store, false)
	if err != nil {
		c.HTML(http.StatusInternalServerError, booksTemplate, gin.H{"Error": err.Error()})
		return
	}
	sort.Slice(books, func(i, j int) bool { return books[i].Title < books[j].Title })
	c.HTML(http.StatusOK, booksTemplate, gin.H{"Books": books})
}

func (s *Server) lookupUser(c *gin.Context) *config.User {
	uid := c.Param("userid")
	u := s.store.UserList.Get(uid)
	if u == nil {
		c.HTML(http.StatusNotFound, errorTemplate, gin.H{"Error": "user not found"})
		return nil
	}
	return u
}
