package cmd

import (
	"fmt"
	"os"

	"github.com/olekukonko/tablewriter"
	"github.com/spf13/cobra"
	"github.com/subdavis/kobo-book-downloader/internal/actions"
	"github.com/subdavis/kobo-book-downloader/internal/config"
)

var userCmd = &cobra.Command{
	Use:   "user",
	Short: "manage user accounts",
}

var userAddCmd = &cobra.Command{
	Use:   "add",
	Short: "add and authenticate a Kobo account",
	RunE: func(cmd *cobra.Command, args []string) error {
		store := storeFromCtx(cmd)
		u := &config.User{}
		if err := actions.CLILogin(u, store, os.Stdout); err != nil {
			return err
		}
		store.UserList.Users = append(store.UserList.Users, u)
		if err := store.Save(); err != nil {
			return err
		}
		fmt.Printf("Added user: %s\n", u.DisplayName())
		return nil
	},
}

var userListCmd = &cobra.Command{
	Use:   "list",
	Short: "list authenticated accounts",
	RunE: func(cmd *cobra.Command, args []string) error {
		store := storeFromCtx(cmd)
		users := store.UserList.Users
		if len(users) == 0 {
			fmt.Println("No users. Run: kobodl user add")
			return nil
		}
		tw := tablewriter.NewWriter(os.Stdout)
		tw.SetHeader([]string{"Email", "User ID", "Authenticated"})
		tw.SetBorder(false)
		for _, u := range users {
			auth := "no"
			if u.IsAuthenticated() {
				auth = "yes"
			}
			tw.Append([]string{u.Email, u.UserId, auth})
		}
		tw.Render()
		return nil
	},
}

var userRemoveCmd = &cobra.Command{
	Use:   "remove <email-or-userid>",
	Short: "remove a user account",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		store := storeFromCtx(cmd)
		u := store.UserList.Get(args[0])
		if u == nil {
			return fmt.Errorf("user %q not found", args[0])
		}
		store.UserList.Remove(u)
		if err := store.Save(); err != nil {
			return err
		}
		fmt.Printf("Removed user: %s\n", args[0])
		return nil
	},
}

func init() {
	userCmd.AddCommand(userAddCmd, userListCmd, userRemoveCmd)
	rootCmd.AddCommand(userCmd)
}
